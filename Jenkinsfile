// Strip common mistake: parameter value "OPENROUTER_CREDENTIALS_ID = OPENROUTER_API_KEY" (Jenkins would look up that full string as credential ID).
def normalizeOpenRouterCredsId = { Object raw ->
    if (raw == null) {
        return ''
    }
    def s = raw.toString().trim()
    if (!s) {
        return ''
    }
    if (s.contains('=')) {
        def parts = s.split('=', 2)
        if (parts.length == 2) {
            s = parts[1].trim()
        }
    }
    s = s.replaceAll('(?i)^OPENROUTER_CREDENTIALS_ID\\s*', '').trim()
    return s
}

// Bind Jenkins Secret text → OPENROUTER_API_KEY for Python / Maestro (optional).
def withOpenRouterCredentials = { Object credsId, Closure action ->
    def id = normalizeOpenRouterCredsId(credsId)
    if (id) {
        try {
            withCredentials([string(credentialsId: id, variable: 'OPENROUTER_API_KEY')]) {
                action()
            }
        } catch (Exception ex) {
            echo "[WARN] OpenRouter credential '${id}' missing/invalid. Continuing without AI key: ${ex.message}"
            action()
        }
    } else {
        action()
    }
}

pipeline {
    agent none

    parameters {
        choice(
            name: 'DEVICES_AGENT',
            choices: ['devices', 'my-pc-devices'],
            description: 'Label of the Jenkins agent connected to real USB phones. Default: devices'
        )
        string(name: 'APP_PACKAGE', defaultValue: 'com.kodaksmile', description: 'App package id for Maestro/app launch checks')
        string(name: 'MAESTRO_CMD', defaultValue: 'maestro.bat', description: 'Maestro launcher (e.g. maestro.bat).')
        string(name: 'MAESTRO_HOME', defaultValue: 'C:\\Users\\HP\\maestro\\maestro\\bin', description: 'Folder containing maestro.bat.')
        string(name: 'ANDROID_HOME', defaultValue: 'C:\\Users\\HP\\AppData\\Local\\Android\\Sdk', description: 'Android SDK root.')
        string(name: 'JAVA_HOME_OVERRIDE', defaultValue: 'C:\\Users\\HP\\.jdks\\jbr-17.0.8', description: 'JDK for Maestro (MAESTRO_JAVA_HOME/JAVA_HOME). Default is jbr-17.0.8.')
        booleanParam(name: 'RUN_NON_PRINTING', defaultValue: true, description: 'Run non-printing flows')
        booleanParam(name: 'RUN_PRINTING', defaultValue: true, description: 'Run printing flows')
        booleanParam(name: 'RUN_AI_ANALYSIS', defaultValue: true, description: 'Test OpenRouter + run intelligent_platform failure analysis')
        booleanParam(name: 'SEND_FINAL_EMAIL', defaultValue: false, description: 'Send final summary email')
        booleanParam(name: 'CLEAR_STATE', defaultValue: true, description: 'Clear app state in suite runners')
        booleanParam(name: 'RETRY_FAILED', defaultValue: false, description: 'Reserved for future retry logic')
        string(
            name: 'OPENROUTER_CREDENTIALS_ID',
            defaultValue: 'OPENROUTER_API_KEY',
            description: 'Jenkins "Secret text" credential ID only (e.g. OPENROUTER_API_KEY). Injects as OPENROUTER_API_KEY. Do not paste the whole parameter line. Leave empty to use env already set on the agent.'
        )
    }

    options {
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        preserveStashes(buildCount: 5)
        buildDiscarder(
            logRotator(
                numToKeepStr: '10',
                artifactNumToKeepStr: '5',
            )
        )
        timeout(time: 180, unit: 'MINUTES')
    }

    triggers {
        cron('H 9 * * *')
        githubPush()
    }

    environment {
        NON_PRINTING_EXIT_CODE = '0'
        PRINTING_EXIT_CODE = '0'
        ANY_TEST_FAILED = '0'
    }

    stages {
        stage('Fetch Code from GitHub') {
            agent { label 'built-in' }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    deleteDir()
                    checkout scm
                    stash name: 'repo', includes: '**/*', useDefaultExcludes: false
                }
            }
        }

        stage('Install Dependencies') {
            agent { label params.DEVICES_AGENT }
            steps {
                deleteDir()
                unstash 'repo'
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    call scripts\\cleanup_c_drive_generated_files.bat PRE "%WORKSPACE%"
                    python -m pip install --upgrade pip || (echo 1> install_failed.flag & exit /b 1)
                    python -m pip install -r scripts/requirements-python.txt || (echo 1> install_failed.flag & exit /b 1)
                    if exist package.json (
                        call npm ci || call npm install || (echo 1> install_failed.flag & exit /b 1)
                    )
                    if exist ai-doctor/package.json (
                        cd ai-doctor
                        call npm ci || call npm install || (echo 1> ..\\install_failed.flag & exit /b 1)
                        cd ..
                    )
                    if not exist build-summary mkdir build-summary
                    """
                }
            }
        }

        stage('Environment Precheck') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    script {
                        def envList = []
                        def maestroJava = (params.JAVA_HOME_OVERRIDE?.trim()) ?: 'C:\\Users\\HP\\.jdks\\jbr-17.0.8'
                        envList << "MAESTRO_JAVA_HOME=${maestroJava}"
                        envList << "JAVA_HOME=${maestroJava}"
                        envList << "PATH+JAVA=${maestroJava}\\bin"
                        if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
                        if (params.ANDROID_HOME?.trim()) {
                            envList << "ANDROID_HOME=${params.ANDROID_HOME}"
                            envList << "ADB_HOME=${params.ANDROID_HOME}\\platform-tools"
                            envList << "PATH+ADB=${params.ANDROID_HOME}\\platform-tools"
                        }
                        withEnv(envList) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            where java
                            java -version
                            call scripts/precheck_environment.bat "${params.MAESTRO_CMD}" "${params.APP_PACKAGE}" || (echo 1> precheck_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                            """
                        }
                    }
                }
            }
        }

        stage('Detect Connected Devices') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    script {
                        def envList = []
                        def maestroJava = (params.JAVA_HOME_OVERRIDE?.trim()) ?: 'C:\\Users\\HP\\.jdks\\jbr-17.0.8'
                        envList << "MAESTRO_JAVA_HOME=${maestroJava}"
                        envList << "JAVA_HOME=${maestroJava}"
                        envList << "PATH+JAVA=${maestroJava}\\bin"
                        if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
                        if (params.ANDROID_HOME?.trim()) {
                            envList << "ANDROID_HOME=${params.ANDROID_HOME}"
                            envList << "ADB_HOME=${params.ANDROID_HOME}\\platform-tools"
                            envList << "PATH+ADB=${params.ANDROID_HOME}\\platform-tools"
                        }
                        withEnv(envList) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            call scripts/list_devices.bat || (echo 1> device_detection_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                            """
                        }
                    }
                }
            }
        }

        stage('Execute Non Printing Flows') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        def envList = []
                        def maestroJava = (params.JAVA_HOME_OVERRIDE?.trim()) ?: 'C:\\Users\\HP\\.jdks\\jbr-17.0.8'
                        envList << "MAESTRO_JAVA_HOME=${maestroJava}"
                        envList << "JAVA_HOME=${maestroJava}"
                        envList << "PATH+JAVA=${maestroJava}\\bin"
                        if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
                        if (params.ANDROID_HOME?.trim()) {
                            envList << "ANDROID_HOME=${params.ANDROID_HOME}"
                            envList << "ADB_HOME=${params.ANDROID_HOME}\\platform-tools"
                            envList << "PATH+ADB=${params.ANDROID_HOME}\\platform-tools"
                        }
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(envList) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                where java
                                call scripts/run_suite_parallel_same_machine.bat nonprinting "Non printing flows" "" "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" || (echo 1> nonprinting_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate Non Printing Artifacts') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py nonprinting "${env.WORKSPACE}" || (echo 1> nonprinting_no_results.flag)
                    if not exist status\\nonprinting__*.txt (echo 1> nonprinting_no_results.flag)
                    if not exist reports\\nonprinting\\results\\*.csv (echo 1> nonprinting_no_results.flag)
                    if not exist reports\\nonprinting\\logs\\*.log (echo 1> nonprinting_no_results.flag)
                    """
                }
            }
        }

        stage('Generate Excel Report for Non Printing') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/nonprinting_summary nonprinting || (echo 1> nonprinting_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Execute Printing Flows on Physical Devices') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        def envList = []
                        def maestroJava = (params.JAVA_HOME_OVERRIDE?.trim()) ?: 'C:\\Users\\HP\\.jdks\\jbr-17.0.8'
                        envList << "MAESTRO_JAVA_HOME=${maestroJava}"
                        envList << "JAVA_HOME=${maestroJava}"
                        envList << "PATH+JAVA=${maestroJava}\\bin"
                        if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
                        if (params.ANDROID_HOME?.trim()) {
                            envList << "ANDROID_HOME=${params.ANDROID_HOME}"
                            envList << "ADB_HOME=${params.ANDROID_HOME}\\platform-tools"
                            envList << "PATH+ADB=${params.ANDROID_HOME}\\platform-tools"
                        }
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(envList) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                where java
                                call scripts/run_suite_parallel_same_machine.bat printing "Printing Flow" "" "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" || (echo 1> printing_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate Printing Artifacts') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py printing "${env.WORKSPACE}" || (echo 1> printing_no_results.flag)
                    if not exist status\\printing__*.txt (echo 1> printing_no_results.flag)
                    if not exist reports\\printing\\results\\*.csv (echo 1> printing_no_results.flag)
                    if not exist reports\\printing\\logs\\*.log (echo 1> printing_no_results.flag)
                    """
                }
            }
        }

        stage('Generate Excel Report for Printing') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/printing_summary printing || (echo 1> printing_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Test AI Connection') {
            when { expression { return params.RUN_AI_ANALYSIS } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/test_ai_connection.py
                            if exist build-summary\\ai_status.txt ( type build-summary\\ai_status.txt ) else ( echo No ai_status.txt )
                            """
                        }
                    }
                }
            }
        }

        stage('AI Failure Analysis + Smart Retry') {
            when { expression { return params.RUN_AI_ANALYSIS } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            if not exist build-summary\\ai_status.txt echo AI_STATUS=FILE_MISSING > build-summary\\ai_status.txt
                            call scripts/run_ai_analysis.bat || (echo 1> ai_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Build Summary') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    if not exist build-summary mkdir build-summary
                    python scripts/generate_build_summary.py status build-summary || (echo 1> summary_failed.flag)
                    if exist scripts\\generate_final_report.py (
                        python scripts/generate_final_report.py . status build-summary\\final_execution_report.xlsx
                    ) else if exist build-summary\\final_execution_report.xlsx (
                        echo final_execution_report already from generate_excel merge.
                    ) else (
                        echo No generate_final_report.py; Excel merge should exist from per-suite report.
                    )
                    """
                }
            }
        }

        stage('Materialize execution_logs.zip for archive and email') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python -c "import sys; from pathlib import Path; r=Path('.'); sys.path.insert(0, str(r.resolve())); from mailout.send_email import build_execution_logs_zip; z=build_execution_logs_zip(r); print('execution_logs.zip =>', z)"
                    """
                }
            }
        }

        // mailout/send_email.py — user/pass from Jenkins credential "gmail-smtp-kodak" (Gmail + App Password). No secrets in this file.
        stage('Send Final Email') {
            when { expression { return params.SEND_FINAL_EMAIL } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withCredentials([usernamePassword(credentialsId: 'gmail-smtp-kodak', usernameVariable: 'B_SMTP_USER', passwordVariable: 'B_SMTP_PASS')]) {
                            withEnv([
                                'SMTP_SERVER=smtp.gmail.com',
                                'SMTP_HOST=smtp.gmail.com',
                                'SMTP_PORT=587',
                                "SMTP_USER=${env.B_SMTP_USER}",
                                "SMTP_PASS=${env.B_SMTP_PASS}",
                                "SENDER_EMAIL=${env.B_SMTP_USER}",
                                "RECEIVER_EMAIL=${env.B_SMTP_USER}",
                                "MAIL_TO=${env.B_SMTP_USER}",
                                'PYTHONIOENCODING=utf-8',
                                'ORCH_EMAIL_STRICT=1',
                                "FINAL_EXECUTION_REPORT_XLSX=${env.WORKSPACE}\\build-summary\\final_execution_report.xlsx",
                            ]) {
                                bat """
                                cd /d "%WORKSPACE%"
                                echo Running send_email with Jenkins credential gmail-smtp-kodak ...
                                python mailout\\send_email.py || (echo 1> email_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Archive Reports & Artifacts') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    archiveArtifacts artifacts: 'build-summary/final_execution_report.xlsx, build-summary/execution_logs.zip, .maestro/screenshots/**, detected_devices.txt', allowEmptyArchive: true
                }
            }
        }

        stage('Finalize Build Result') {
            agent { label params.DEVICES_AGENT }
            steps {
                script {
                    def unstableFlags = [
                        'nonprinting_failed.flag', 'nonprinting_no_results.flag', 'nonprinting_report_failed.flag',
                        'printing_failed.flag', 'printing_no_results.flag', 'printing_report_failed.flag',
                        'summary_failed.flag', 'ai_failed.flag', 'email_failed.flag', 'pipeline_failed.flag',
                    ]
                    def u = false
                    unstableFlags.each { f -> if (fileExists(f)) { u = true } }
                    if (fileExists('install_failed.flag') || fileExists('precheck_failed.flag') || fileExists('device_detection_failed.flag')) {
                        currentBuild.result = 'FAILURE'
                    } else if (u) {
                        currentBuild.result = 'UNSTABLE'
                    } else {
                        currentBuild.result = 'SUCCESS'
                    }
                }
            }
        }

        stage('Post-build workspace cleanup (C: agent disk)') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    call scripts\\cleanup_c_drive_generated_files.bat POST "%WORKSPACE%"
                    """
                }
            }
        }
    }

    post {
        always { echo "Build: ${currentBuild.currentResult}" }
    }
}
