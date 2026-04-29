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
                    bat """call scripts\\jenkins_ci_install.bat "${env.WORKSPACE}" """
                }
            }
        }

        stage('Environment Precheck') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    script {
                        withEnv(maestroEnvList()) {
                            bat """call scripts\\jenkins_ci_precheck.bat "${env.WORKSPACE}" "${params.MAESTRO_CMD}" "${params.APP_PACKAGE}" """
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
                            bat """call scripts\\jenkins_ci_devices.bat "${env.WORKSPACE}" """
                        }
                    }
                }
            }
        }

        stage('Camera') {
            when { expression { return params.RUN_ATP_CAMERA } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all Camera "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
                        }
                    }
                }
            }
        }

        stage('Collage') {
            when { expression { return params.RUN_ATP_COLLAGE } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all Collage "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
                        }
                    }
                }
            }
        }

        stage('Connection') {
            when { expression { return params.RUN_ATP_CONNECTION } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all Connection "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
                        }
                    }
                }
            }
        }

        stage('Editing') {
            when { expression { return params.RUN_ATP_EDITING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all Editing "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
                        }
                    }
                }
            }
        }

        stage('Onboarding') {
            when { expression { return params.RUN_ATP_ONBOARDING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all Onboarding "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
                        }
                    }
                }
            }
        }

        stage('Precut') {
            when { expression { return params.RUN_ATP_PRECUT } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all Precut "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
                        }
                    }
                }
            }
        }

        stage('Printing') {
            when { expression { return params.RUN_ATP_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all Printing "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
                        }
                    }
                }
            }
        }

        stage('Settings') {
            when { expression { return params.RUN_ATP_SETTINGS } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all Settings "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
                        }
                    }
                }
            }
        }

        stage('SignUp_Login') {
            when { expression { return params.RUN_ATP_SIGNUP_LOGIN } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    script {
                        withOpenRouterCredentials(params.OPENROUTER_CREDENTIALS_ID) {
                            withEnv(maestroEnvList()) {
                                bat """cd /d "${env.WORKSPACE}" && python scripts/jenkins_atp_stage.py all SignUp_Login "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" """
                            }
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
                            bat """call scripts\\jenkins_ci_merge_atp.bat "${env.WORKSPACE}" """
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
                            bat """call scripts\\jenkins_ci_ai_probe.bat "${env.WORKSPACE}" """
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
                            bat """call scripts\\jenkins_ci_ai_analysis.bat "${env.WORKSPACE}" """
                        }
                    }
                }
            }
        }

        stage('Build Summary') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """call scripts\\jenkins_ci_build_summary.bat "${env.WORKSPACE}" """
                }
            }
        }

        stage('Materialize execution_logs.zip for archive and email') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat """call scripts\\jenkins_ci_zip_logs.bat "${env.WORKSPACE}" """
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
                                bat """call scripts\\jenkins_ci_send_email.bat "${env.WORKSPACE}" """
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
                    bat """call scripts\\jenkins_ci_cleanup_post.bat "${env.WORKSPACE}" """
                }
            }
        }
    }

    post {
        always { echo "Build: ${currentBuild.currentResult}" }
    }
}
