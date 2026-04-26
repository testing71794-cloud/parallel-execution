// Strip common mistake: parameter value "OPENROUTER_CREDENTIALS_ID = OPENROUTER_API_KEY"
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

def withOpenRouterCredentials = { String credsId, Closure action ->
    def id = normalizeOpenRouterCredsId(credsId)
    if (id) {
        withCredentials([string(credentialsId: id, variable: 'OPENROUTER_API_KEY')]) {
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
            choices: ['devices', 'built-in'],
            description: 'devices = agent with USB phones / adb'
        )
        string(name: 'APP_PACKAGE', defaultValue: 'com.kodaksmile', description: 'App package id for Maestro/app launch checks')
        string(name: 'MAESTRO_CMD', defaultValue: 'maestro.bat', description: 'Maestro launcher (e.g. maestro.bat)')
        string(name: 'MAESTRO_HOME', defaultValue: 'C:\\Users\\HP\\maestro\\maestro\\bin', description: 'Folder containing maestro.bat (optional if maestro is on PATH)')
        string(name: 'ANDROID_HOME', defaultValue: 'C:\\Users\\HP\\AppData\\Local\\Android\\Sdk', description: 'Android SDK root')
        string(name: 'JAVA_HOME_OVERRIDE', defaultValue: '', description: 'Optional JDK for Maestro (MAESTRO_JAVA_HOME)')
        booleanParam(name: 'RUN_NON_PRINTING', defaultValue: true, description: 'Run non-printing flows (Python parallel orchestrator)')
        booleanParam(name: 'RUN_PRINTING', defaultValue: true, description: 'Run printing flows (Python parallel orchestrator)')
        booleanParam(name: 'RUN_AI_ANALYSIS', defaultValue: true, description: 'Per-flow OpenRouter AI (429: 3 tries, 5s backoff)')
        booleanParam(name: 'SEND_FINAL_EMAIL', defaultValue: false, description: 'Send email with final_execution_report.xlsx')
        string(
            name: 'OPENROUTER_CREDENTIALS_ID',
            defaultValue: 'OPENROUTER_API_KEY',
            description: 'Jenkins Secret text credential ID → OPENROUTER_API_KEY'
        )
        string(
            name: 'SMTP_CREDENTIALS_ID',
            defaultValue: '',
            description: 'Optional Jenkins Username/Password ID for SMTP (username=sender, password=app password). If empty, uses SMTP_* env on the agent.'
        )
        string(
            name: 'MAIL_TO_OVERRIDE',
            defaultValue: '',
            description: 'Optional RECEIVER_EMAIL override (defaults to SMTP user when using SMTP_CREDENTIALS_ID)'
        )
        string(
            name: 'SMTP_SERVER',
            defaultValue: 'smtp.gmail.com',
            description: 'SMTP host when using SMTP_CREDENTIALS_ID or agent env'
        )
        string(
            name: 'SMTP_PORT',
            defaultValue: '587',
            description: 'SMTP port'
        )
    }

    options {
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        preserveStashes(buildCount: 5)
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 180, unit: 'MINUTES')
    }

    triggers {
        cron('H 9 * * *')
        githubPush()
    }

    stages {
        stage('Checkout Code') {
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
                    """
                }
            }
        }

        stage('Environment Validation') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    script {
                        def envList = []
                        if (params.JAVA_HOME_OVERRIDE?.trim()) {
                            envList << "MAESTRO_JAVA_HOME=${params.JAVA_HOME_OVERRIDE}"
                            envList << "JAVA_HOME=${params.JAVA_HOME_OVERRIDE}"
                            envList << "PATH+JAVA=${params.JAVA_HOME_OVERRIDE}\\bin"
                        }
                        if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
                        if (params.ANDROID_HOME?.trim()) { envList << "ANDROID_HOME=${params.ANDROID_HOME}" }
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

        stage('Cleanup Previous Execution') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python execution/cleanup_previous_run.py --repo-root "${env.WORKSPACE}" || (echo 1> cleanup_failed.flag & exit /b 1)
                    """
                }
            }
        }

        stage('Detect Connected Devices') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    script {
                        def envList = []
                        if (params.JAVA_HOME_OVERRIDE?.trim()) {
                            envList << "MAESTRO_JAVA_HOME=${params.JAVA_HOME_OVERRIDE}"
                            envList << "JAVA_HOME=${params.JAVA_HOME_OVERRIDE}"
                            envList << "PATH+JAVA=${params.JAVA_HOME_OVERRIDE}\\bin"
                        }
                        if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
                        if (params.ANDROID_HOME?.trim()) {
                            envList << "ANDROID_HOME=${params.ANDROID_HOME}"
                            envList << "PATH+PLATFORM_TOOLS=${params.ANDROID_HOME}\\platform-tools"
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

        stage('Execute Non-Printing Flows (Parallel)') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        def envList = []
                        if (params.JAVA_HOME_OVERRIDE?.trim()) {
                            envList << "MAESTRO_JAVA_HOME=${params.JAVA_HOME_OVERRIDE}"
                            envList << "JAVA_HOME=${params.JAVA_HOME_OVERRIDE}"
                            envList << "PATH+JAVA=${params.JAVA_HOME_OVERRIDE}\\bin"
                        }
                        if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
                        if (params.ANDROID_HOME?.trim()) {
                            envList << "ANDROID_HOME=${params.ANDROID_HOME}"
                            envList << "PATH+PLATFORM_TOOLS=${params.ANDROID_HOME}\\platform-tools"
                        }
                        def mh = params.MAESTRO_HOME?.trim()
                        def mc = params.MAESTRO_CMD?.trim() ?: 'maestro.bat'
                        def maestroExe = mh ? "${mh}\\${mc}" : mc
                        def noAi = params.RUN_AI_ANALYSIS ? '' : '--no-ai'
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(envList) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                where java
                                if defined ANDROID_HOME set "PATH=%ANDROID_HOME%\\platform-tools;%PATH%"
                                python execution/run_parallel_devices.py --repo-root "${env.WORKSPACE}" --flows-file execution/nonprinting_flows.txt --maestro "${maestroExe}" --config config.yaml --excel-out final_execution_report.xlsx --no-clean ${noAi}
                                if errorlevel 1 echo 1> orch_nonprinting_failed.flag
                                exit /b 0
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Execute Printing Flows (Parallel)') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        def envList = []
                        if (params.JAVA_HOME_OVERRIDE?.trim()) {
                            envList << "MAESTRO_JAVA_HOME=${params.JAVA_HOME_OVERRIDE}"
                            envList << "JAVA_HOME=${params.JAVA_HOME_OVERRIDE}"
                            envList << "PATH+JAVA=${params.JAVA_HOME_OVERRIDE}\\bin"
                        }
                        if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
                        if (params.ANDROID_HOME?.trim()) {
                            envList << "ANDROID_HOME=${params.ANDROID_HOME}"
                            envList << "PATH+PLATFORM_TOOLS=${params.ANDROID_HOME}\\platform-tools"
                        }
                        def mh = params.MAESTRO_HOME?.trim()
                        def mc = params.MAESTRO_CMD?.trim() ?: 'maestro.bat'
                        def maestroExe = mh ? "${mh}\\${mc}" : mc
                        def noAi = params.RUN_AI_ANALYSIS ? '' : '--no-ai'
                        def noPrime = (params.RUN_NON_PRINTING && params.RUN_PRINTING) ? '--no-prime' : ''
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(envList) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                where java
                                if defined ANDROID_HOME set "PATH=%ANDROID_HOME%\\platform-tools;%PATH%"
                                python execution/run_parallel_devices.py --repo-root "${env.WORKSPACE}" --flows-file execution/printing_flows.txt --maestro "${maestroExe}" --config config.yaml --excel-out final_execution_report.xlsx --no-clean ${noPrime} ${noAi}
                                if errorlevel 1 echo 1> orch_printing_failed.flag
                                exit /b 0
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Generate Final Summary') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    if not exist build-summary mkdir build-summary
                    python scripts/summarize_final_excel.py final_execution_report.xlsx build-summary/execution_counts.txt || (echo 1> summary_failed.flag)
                    if exist build-summary\\execution_counts.txt type build-summary\\execution_counts.txt
                    """
                }
            }
        }

        stage('Send Email') {
            when { expression { return params.SEND_FINAL_EMAIL } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        def smtpId = params.SMTP_CREDENTIALS_ID?.trim()
                        def mailTo = params.MAIL_TO_OVERRIDE?.trim()
                        def smtpServer = params.SMTP_SERVER?.trim() ?: 'smtp.gmail.com'
                        def smtpPort = params.SMTP_PORT?.trim() ?: '587'
                        if (smtpId) {
                            withCredentials([usernamePassword(credentialsId: smtpId, usernameVariable: 'SMTP_JENKINS_USER', passwordVariable: 'SMTP_JENKINS_PASS')]) {
                                def receiver = mailTo ?: env.SMTP_JENKINS_USER
                                withEnv([
                                    "SMTP_SERVER=${smtpServer}",
                                    "SMTP_PORT=${smtpPort}",
                                    "SMTP_USER=${env.SMTP_JENKINS_USER}",
                                    "SMTP_PASS=${env.SMTP_JENKINS_PASS}",
                                    "SENDER_EMAIL=${env.SMTP_JENKINS_USER}",
                                    "RECEIVER_EMAIL=${receiver}",
                                    "FINAL_EXECUTION_REPORT_XLSX=${env.WORKSPACE}\\final_execution_report.xlsx",
                                    'PYTHONIOENCODING=utf-8',
                                ]) {
                                    bat """
                                    cd /d "${env.WORKSPACE}"
                                    python mailout/send_email.py || (echo 1> email_failed.flag)
                                    """
                                }
                            }
                        } else {
                            withEnv([
                                "SMTP_SERVER=${smtpServer}",
                                "SMTP_PORT=${smtpPort}",
                                "FINAL_EXECUTION_REPORT_XLSX=${env.WORKSPACE}\\final_execution_report.xlsx",
                                'PYTHONIOENCODING=utf-8',
                            ]) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                python mailout/send_email.py || (echo 1> email_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Archive Reports') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    archiveArtifacts artifacts: 'logs/**, reports/**, build-summary/**, final_execution_report.xlsx, detected_devices.txt, *.flag, *.failed', allowEmptyArchive: true
                }
            }
        }

        stage('Finalize Build') {
            agent { label params.DEVICES_AGENT }
            steps {
                script {
                    def unstableFlags = [
                        'orch_nonprinting_failed.flag',
                        'orch_printing_failed.flag',
                        'summary_failed.flag',
                        'email_failed.flag',
                        'pipeline_failed.flag',
                    ]
                    def u = false
                    unstableFlags.each { f -> if (fileExists(f)) { u = true } }
                    if (fileExists('install_failed.flag') || fileExists('precheck_failed.flag') || fileExists('device_detection_failed.flag') || fileExists('cleanup_failed.flag')) {
                        currentBuild.result = 'FAILURE'
                    } else if (u) {
                        currentBuild.result = 'UNSTABLE'
                    } else {
                        currentBuild.result = 'SUCCESS'
                    }
                }
            }
        }
    }

    post {
        always { echo "Build: ${currentBuild.currentResult}" }
    }
}
