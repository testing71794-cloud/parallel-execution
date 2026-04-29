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

/** Shared Maestro/Java/ADB env list — deduped to avoid Jenkins CPS MethodTooLargeException on large pipelines. */
def maestroEnvList() {
    def maestroJava = (params.JAVA_HOME_OVERRIDE?.trim()) ?: 'C:\\Users\\HP\\.jdks\\jbr-17.0.8'
    def envList = []
    envList << "MAESTRO_JAVA_HOME=${maestroJava}"
    envList << "JAVA_HOME=${maestroJava}"
    envList << "PATH+JAVA=${maestroJava}\\bin"
    if (params.MAESTRO_HOME?.trim()) { envList << "MAESTRO_HOME=${params.MAESTRO_HOME}" }
    if (params.ANDROID_HOME?.trim()) {
        envList << "ANDROID_HOME=${params.ANDROID_HOME}"
        envList << "ADB_HOME=${params.ANDROID_HOME}\\platform-tools"
        envList << "PATH+ADB=${params.ANDROID_HOME}\\platform-tools"
    }
    return envList
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
        booleanParam(name: 'RUN_ATP_CAMERA', defaultValue: true, description: 'ATP TestCase Flows: Camera')
        booleanParam(name: 'RUN_ATP_COLLAGE', defaultValue: true, description: 'ATP TestCase Flows: Collage')
        booleanParam(name: 'RUN_ATP_CONNECTION', defaultValue: true, description: 'ATP TestCase Flows: Connection')
        booleanParam(name: 'RUN_ATP_EDITING', defaultValue: true, description: 'ATP TestCase Flows: Editing')
        booleanParam(name: 'RUN_ATP_ONBOARDING', defaultValue: true, description: 'ATP TestCase Flows: Onboarding')
        booleanParam(name: 'RUN_ATP_PRECUT', defaultValue: true, description: 'ATP TestCase Flows: Precut')
        booleanParam(name: 'RUN_ATP_PRINTING', defaultValue: true, description: 'ATP TestCase Flows: Printing (folder under ATP TestCase Flows only)')
        booleanParam(name: 'RUN_ATP_SETTINGS', defaultValue: true, description: 'ATP TestCase Flows: Settings')
        booleanParam(name: 'RUN_ATP_SIGNUP_LOGIN', defaultValue: true, description: 'ATP TestCase Flows: SignUp_Login')
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
        // Keep stash copies low: full repo stashes are large; excludes shrink controller disk use.
        preserveStashes(buildCount: 2)
        buildDiscarder(
            logRotator(
                numToKeepStr: '10',
                // Fewer archived copies of execution_logs.zip / screenshots / Excel on Jenkins home disk.
                artifactNumToKeepStr: '3',
            )
        )
        timeout(time: 180, unit: 'MINUTES')
    }

    triggers {
        cron('H 9 * * *')
        githubPush()
    }

    stages {
        stage('Fetch Code from GitHub') {
            agent { label 'built-in' }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    deleteDir()
                    checkout scm
                    // Stash sources only: exclude .git, deps, workspace screenshots (.maestro), generated dirs (docs/disk_cleanup_guide.md).
                    stash name: 'repo', includes: '**/*', excludes: '**/.git/**,**/node_modules/**,**/.maestro/**,**/reports/**,**/build-summary/**,**/status/**,**/logs/**,**/collected-artifacts/**,**/test-results/**,**/maestro-report/**,**/*.zip', useDefaultExcludes: false
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
                    echo === SAFE DISK CLEANUP PRE ===
                    call scripts\\safe_disk_cleanup.bat PRE "%WORKSPACE%"
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
                        withEnv(maestroEnvList()) {
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
                        withEnv(maestroEnvList()) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            call scripts/list_devices.bat || (echo 1> device_detection_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP Camera Flows') {
            when { expression { return params.RUN_ATP_CAMERA } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP CAMERA FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "Camera" || (echo 1> atp_camera_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP Camera Artifacts') {
            when { expression { return params.RUN_ATP_CAMERA } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_camera "${env.WORKSPACE}" || (echo 1> atp_camera_no_results.flag)
                    if not exist status\\atp_camera__*.txt (echo 1> atp_camera_no_results.flag)
                    if not exist reports\\atp_camera\\results\\*.csv (echo 1> atp_camera_no_results.flag)
                    if not exist reports\\atp_camera\\logs\\*.log (echo 1> atp_camera_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP Camera Excel Report') {
            when { expression { return params.RUN_ATP_CAMERA } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_camera_summary atp_camera Camera --skip-if-empty || (echo 1> atp_camera_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP Collage Flows') {
            when { expression { return params.RUN_ATP_COLLAGE } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP COLLAGE FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "Collage" || (echo 1> atp_collage_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP Collage Artifacts') {
            when { expression { return params.RUN_ATP_COLLAGE } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_collage "${env.WORKSPACE}" || (echo 1> atp_collage_no_results.flag)
                    if not exist status\\atp_collage__*.txt (echo 1> atp_collage_no_results.flag)
                    if not exist reports\\atp_collage\\results\\*.csv (echo 1> atp_collage_no_results.flag)
                    if not exist reports\\atp_collage\\logs\\*.log (echo 1> atp_collage_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP Collage Excel Report') {
            when { expression { return params.RUN_ATP_COLLAGE } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_collage_summary atp_collage Collage --skip-if-empty || (echo 1> atp_collage_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP Connection Flows') {
            when { expression { return params.RUN_ATP_CONNECTION } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP CONNECTION FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "Connection" || (echo 1> atp_connection_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP Connection Artifacts') {
            when { expression { return params.RUN_ATP_CONNECTION } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_connection "${env.WORKSPACE}" || (echo 1> atp_connection_no_results.flag)
                    if not exist status\\atp_connection__*.txt (echo 1> atp_connection_no_results.flag)
                    if not exist reports\\atp_connection\\results\\*.csv (echo 1> atp_connection_no_results.flag)
                    if not exist reports\\atp_connection\\logs\\*.log (echo 1> atp_connection_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP Connection Excel Report') {
            when { expression { return params.RUN_ATP_CONNECTION } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_connection_summary atp_connection Connection --skip-if-empty || (echo 1> atp_connection_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP Editing Flows') {
            when { expression { return params.RUN_ATP_EDITING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP EDITING FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "Editing" || (echo 1> atp_editing_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP Editing Artifacts') {
            when { expression { return params.RUN_ATP_EDITING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_editing "${env.WORKSPACE}" || (echo 1> atp_editing_no_results.flag)
                    if not exist status\\atp_editing__*.txt (echo 1> atp_editing_no_results.flag)
                    if not exist reports\\atp_editing\\results\\*.csv (echo 1> atp_editing_no_results.flag)
                    if not exist reports\\atp_editing\\logs\\*.log (echo 1> atp_editing_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP Editing Excel Report') {
            when { expression { return params.RUN_ATP_EDITING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_editing_summary atp_editing Editing --skip-if-empty || (echo 1> atp_editing_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP Onboarding Flows') {
            when { expression { return params.RUN_ATP_ONBOARDING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP ONBOARDING FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "Onboarding" || (echo 1> atp_onboarding_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP Onboarding Artifacts') {
            when { expression { return params.RUN_ATP_ONBOARDING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_onboarding "${env.WORKSPACE}" || (echo 1> atp_onboarding_no_results.flag)
                    if not exist status\\atp_onboarding__*.txt (echo 1> atp_onboarding_no_results.flag)
                    if not exist reports\\atp_onboarding\\results\\*.csv (echo 1> atp_onboarding_no_results.flag)
                    if not exist reports\\atp_onboarding\\logs\\*.log (echo 1> atp_onboarding_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP Onboarding Excel Report') {
            when { expression { return params.RUN_ATP_ONBOARDING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_onboarding_summary atp_onboarding Onboarding --skip-if-empty || (echo 1> atp_onboarding_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP Precut Flows') {
            when { expression { return params.RUN_ATP_PRECUT } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP PRECUT FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "Precut" || (echo 1> atp_precut_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP Precut Artifacts') {
            when { expression { return params.RUN_ATP_PRECUT } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_precut "${env.WORKSPACE}" || (echo 1> atp_precut_no_results.flag)
                    if not exist status\\atp_precut__*.txt (echo 1> atp_precut_no_results.flag)
                    if not exist reports\\atp_precut\\results\\*.csv (echo 1> atp_precut_no_results.flag)
                    if not exist reports\\atp_precut\\logs\\*.log (echo 1> atp_precut_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP Precut Excel Report') {
            when { expression { return params.RUN_ATP_PRECUT } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_precut_summary atp_precut Precut --skip-if-empty || (echo 1> atp_precut_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP Printing Flows') {
            when { expression { return params.RUN_ATP_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP PRINTING FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "Printing" || (echo 1> atp_printing_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP Printing Artifacts') {
            when { expression { return params.RUN_ATP_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_printing "${env.WORKSPACE}" || (echo 1> atp_printing_no_results.flag)
                    if not exist status\\atp_printing__*.txt (echo 1> atp_printing_no_results.flag)
                    if not exist reports\\atp_printing\\results\\*.csv (echo 1> atp_printing_no_results.flag)
                    if not exist reports\\atp_printing\\logs\\*.log (echo 1> atp_printing_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP Printing Excel Report') {
            when { expression { return params.RUN_ATP_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_printing_summary atp_printing Printing --skip-if-empty || (echo 1> atp_printing_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP Settings Flows') {
            when { expression { return params.RUN_ATP_SETTINGS } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP SETTINGS FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "Settings" || (echo 1> atp_settings_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP Settings Artifacts') {
            when { expression { return params.RUN_ATP_SETTINGS } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_settings "${env.WORKSPACE}" || (echo 1> atp_settings_no_results.flag)
                    if not exist status\\atp_settings__*.txt (echo 1> atp_settings_no_results.flag)
                    if not exist reports\\atp_settings\\results\\*.csv (echo 1> atp_settings_no_results.flag)
                    if not exist reports\\atp_settings\\logs\\*.log (echo 1> atp_settings_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP Settings Excel Report') {
            when { expression { return params.RUN_ATP_SETTINGS } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_settings_summary atp_settings Settings --skip-if-empty || (echo 1> atp_settings_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Run ATP SignUp_Login Flows') {
            when { expression { return params.RUN_ATP_SIGNUP_LOGIN } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """
                                cd /d "${env.WORKSPACE}"
                                echo === RUN ATP SIGNUP_LOGIN FLOWS ===
                                call scripts/run_atp_testcase_flows.bat "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" "SignUp_Login" || (echo 1> atp_signup_login_failed.flag)
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Validate ATP SignUp_Login Artifacts') {
            when { expression { return params.RUN_ATP_SIGNUP_LOGIN } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/validate_suite_artifacts.py atp_signup_login "${env.WORKSPACE}" || (echo 1> atp_signup_login_no_results.flag)
                    if not exist status\\atp_signup_login__*.txt (echo 1> atp_signup_login_no_results.flag)
                    if not exist reports\\atp_signup_login\\results\\*.csv (echo 1> atp_signup_login_no_results.flag)
                    if not exist reports\\atp_signup_login\\logs\\*.log (echo 1> atp_signup_login_no_results.flag)
                    """
                }
            }
        }

        stage('Generate ATP SignUp_Login Excel Report') {
            when { expression { return params.RUN_ATP_SIGNUP_LOGIN } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            if not exist build-summary mkdir build-summary
                            python scripts/generate_excel_report.py status reports/atp_signup_login_summary atp_signup_login SignUp_Login --skip-if-empty || (echo 1> atp_signup_login_report_failed.flag)
                            """
                        }
                    }
                }
            }
        }

        stage('Generate ATP TestCase Excel Reports') {
            when {
                expression {
                    return params.RUN_ATP_CAMERA || params.RUN_ATP_COLLAGE || params.RUN_ATP_CONNECTION ||
                        params.RUN_ATP_EDITING || params.RUN_ATP_ONBOARDING || params.RUN_ATP_PRECUT ||
                        params.RUN_ATP_PRINTING || params.RUN_ATP_SETTINGS || params.RUN_ATP_SIGNUP_LOGIN
                }
            }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            echo === GENERATE ATP TESTCASE EXCEL REPORTS ===
                            if exist build-summary\\atp_suite_labels.json (
                                python scripts/generate_atp_excel_reports.py . || (echo 1> atp_report_failed.flag)
                            ) else (
                                echo [ATP Excel] No atp_suite_labels.json — ATP had no flows or was skipped. OK.
                            )
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
                    def atpSuiteIds = [
                        'atp_camera', 'atp_collage', 'atp_connection', 'atp_editing', 'atp_onboarding',
                        'atp_precut', 'atp_printing', 'atp_settings', 'atp_signup_login',
                    ]
                    def atpFlags = []
                    atpSuiteIds.each { s ->
                        atpFlags.add("${s}_failed.flag")
                        atpFlags.add("${s}_no_results.flag")
                        atpFlags.add("${s}_report_failed.flag")
                    }
                    def unstableFlags = [
                        'atp_report_failed.flag',
                        'summary_failed.flag', 'ai_failed.flag', 'email_failed.flag', 'pipeline_failed.flag',
                    ] + atpFlags
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

        // Runs after archiveArtifacts: frees agent workspace only (Jenkins archived builds unchanged).
        stage('Post-build workspace cleanup (C: agent disk)') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    echo === SAFE DISK CLEANUP POST ===
                    call scripts\\safe_disk_cleanup.bat POST "%WORKSPACE%"
                    echo === DISK USAGE REPORT ===
                    call scripts\\safe_disk_cleanup.bat REPORT "%WORKSPACE%"
                    """
                }
            }
        }
    }

    post {
        always { echo "Build: ${currentBuild.currentResult}" }
    }
}
