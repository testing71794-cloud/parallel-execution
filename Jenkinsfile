pipeline {
    agent none

    triggers {
        cron('H 9 * * *')
    }

    options {
        timestamps()
        disableConcurrentBuilds()
        ansiColor('xterm')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        choice(name: 'RUN_MODE', choices: ['same_machine_sequential', 'multi_agent_parallel'], description: 'same_machine_sequential = stable on one USB PC. multi_agent_parallel = one Jenkins agent per device.')
        choice(name: 'SUITE', choices: ['both', 'nonprinting', 'printing'], description: 'Which suites to run.')
        string(name: 'DEVICES_AGENT', defaultValue: 'devices', description: 'Label for the USB device machine when RUN_MODE=same_machine_sequential.')
        string(name: 'DEVICE1_LABEL', defaultValue: 'device-agent-1', description: 'Agent label for device 1 when RUN_MODE=multi_agent_parallel.')
        string(name: 'DEVICE2_LABEL', defaultValue: 'device-agent-2', description: 'Agent label for device 2 when RUN_MODE=multi_agent_parallel.')
        string(name: 'DEVICE1_ID', defaultValue: '3C1625009Q500000', description: 'ADB device ID for device 1 in multi-agent mode.')
        string(name: 'DEVICE2_ID', defaultValue: 'RZCWA2B05RB', description: 'ADB device ID for device 2 in multi-agent mode.')
        booleanParam(name: 'AI_ANALYSIS', defaultValue: true, description: 'Run ai-doctor at the end when tests fail.')
        booleanParam(name: 'RETRY_FAILED', defaultValue: true, description: 'Retry a failed flow once before marking final failure.')
        choice(name: 'SEND_EMAIL_MODE', choices: ['failed_only', 'always', 'never'], description: 'When to send email summary.')
        string(name: 'MAESTRO_CMD', defaultValue: '', description: 'Optional override. Leave blank to auto-detect maestro.')
        string(name: 'APP_PACKAGE', defaultValue: 'com.kodaksmile', description: 'Optional app package for launch validation.')
        string(name: 'PROJECT_SUBDIR', defaultValue: '', description: 'Optional repo subfolder if the project is not at workspace root.')
        string(name: 'EMAIL_TO', defaultValue: 'your-email@example.com', description: 'Summary email recipient(s). Comma separated.')
    }

    environment {
        PIPELINE_FAILED = '0'
        AI_FAILED = '0'
    }

    stages {
        stage('Checkout Source') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                checkout scm
                stash name: 'source-code', includes: '**/*'
            }
        }

        stage('Precheck - Controller') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'source-code'
                script {
                    def projectRoot = getProjectRoot()
                    echo "Controller project root: ${projectRoot}"
                    if (!fileExists("${projectRoot}/scripts")) {
                        error "scripts folder not found under ${projectRoot}"
                    }
                }
            }
        }

        stage('Precheck - Device Side') {
            parallel {
                stage('Same Machine Devices Agent') {
                    when { expression { params.RUN_MODE == 'same_machine_sequential' } }
                    agent { label params.DEVICES_AGENT }
                    steps {
                        deleteDir()
                        unstash 'source-code'
                        script {
                            def projectRoot = getProjectRoot()
                            bat """
                            cd /d "${projectRoot}"
                            call scripts\\precheck_environment.bat "${resolveMaestroCmd()}" "${params.APP_PACKAGE}"
                            """
                        }
                    }
                }

                stage('Multi Agent Device 1') {
                    when { expression { params.RUN_MODE == 'multi_agent_parallel' } }
                    agent { label params.DEVICE1_LABEL }
                    steps {
                        deleteDir()
                        unstash 'source-code'
                        script {
                            def projectRoot = getProjectRoot()
                            bat """
                            cd /d "${projectRoot}"
                            call scripts\\precheck_environment.bat "${resolveMaestroCmd()}" "${params.APP_PACKAGE}" "${params.DEVICE1_ID}"
                            """
                        }
                    }
                }

                stage('Multi Agent Device 2') {
                    when { expression { params.RUN_MODE == 'multi_agent_parallel' } }
                    agent { label params.DEVICE2_LABEL }
                    steps {
                        deleteDir()
                        unstash 'source-code'
                        script {
                            def projectRoot = getProjectRoot()
                            bat """
                            cd /d "${projectRoot}"
                            call scripts\\precheck_environment.bat "${resolveMaestroCmd()}" "${params.APP_PACKAGE}" "${params.DEVICE2_ID}"
                            """
                        }
                    }
                }
            }
        }

        stage('Run Non-Printing') {
            when { expression { params.SUITE in ['both', 'nonprinting'] } }
            steps {
                script {
                    if (params.RUN_MODE == 'same_machine_sequential') {
                        runSuiteSameMachine('nonprinting', 'Non printing flows')
                    } else {
                        runSuiteMultiAgent('nonprinting', 'Non printing flows')
                    }
                }
            }
        }

        stage('Run Printing') {
            when { expression { params.SUITE in ['both', 'printing'] } }
            steps {
                script {
                    if (params.RUN_MODE == 'same_machine_sequential') {
                        runSuiteSameMachine('printing', 'Printing Flow')
                    } else {
                        runSuiteMultiAgent('printing', 'Printing Flow')
                    }
                }
            }
        }

        stage('Generate Build Summary') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'source-code'
                script {
                    def projectRoot = getProjectRoot()
                    bat """
                    cd /d "${projectRoot}"
                    if not exist collected-artifacts mkdir collected-artifacts
                    python scripts\\generate_build_summary.py collected-artifacts build-summary
                    """
                    stash name: 'summary-artifacts', includes: "${projectRoot}/build-summary/**", allowEmpty: true
                }
            }
        }

        stage('Run AI Analysis') {
            when { expression { params.AI_ANALYSIS && fileExists("${getProjectRoot()}/pipeline_failed.flag") } }
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'source-code'
                script {
                    def projectRoot = getProjectRoot()
                    catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                        bat """
                        cd /d "${projectRoot}"
                        call scripts\\run_ai_analysis.bat
                        if errorlevel 1 (
                            echo 1> ai_failed.flag
                            exit /b 0
                        )
                        """
                    }
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: '**/ai-doctor/artifacts/**, **/ai_failed.flag', allowEmptyArchive: true
                }
            }
        }

        stage('Finalize Build Result') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'source-code'
                script {
                    def projectRoot = getProjectRoot()
                    def pipelineFailed = fileExists("${projectRoot}/pipeline_failed.flag")
                    def aiFailed = fileExists("${projectRoot}/ai_failed.flag")

                    if (pipelineFailed) {
                        currentBuild.result = 'FAILURE'
                    } else if (aiFailed) {
                        currentBuild.result = 'UNSTABLE'
                    } else {
                        currentBuild.result = 'SUCCESS'
                    }

                    echo "Pipeline failed flag = ${pipelineFailed}"
                    echo "AI failed flag = ${aiFailed}"
                    echo "Final result = ${currentBuild.result}"
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: '**/collected-artifacts/**, **/build-summary/**, **/*.flag', allowEmptyArchive: true
        }

        success {
            script {
                if (params.SEND_EMAIL_MODE == 'always') {
                    sendSummaryEmail('SUCCESS')
                }
            }
        }

        unstable {
            script {
                if (params.SEND_EMAIL_MODE != 'never') {
                    sendSummaryEmail('UNSTABLE')
                }
            }
        }

        failure {
            script {
                if (params.SEND_EMAIL_MODE != 'never') {
                    sendSummaryEmail('FAILURE')
                }
            }
        }
    }
}

def getProjectRoot() {
    return params.PROJECT_SUBDIR?.trim() ? "${env.WORKSPACE}\\${params.PROJECT_SUBDIR.trim()}" : env.WORKSPACE
}

def resolveMaestroCmd() {
    return params.MAESTRO_CMD?.trim() ? params.MAESTRO_CMD.trim() : ""
}

def runSuiteSameMachine(String suiteName, String suiteDir) {
    node(params.DEVICES_AGENT) {
        deleteDir()
        unstash 'source-code'
        def projectRoot = getProjectRoot()

        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
            bat """
            cd /d "${projectRoot}"
            if not exist collected-artifacts mkdir collected-artifacts
            call scripts\\run_suite_same_machine.bat "${suiteName}" "${suiteDir}" "${resolveMaestroCmd()}" "${params.APP_PACKAGE}" "${params.RETRY_FAILED}"
            if errorlevel 1 (
                echo 1> pipeline_failed.flag
                exit /b 0
            )
            """
        }

        stash name: "suite-${suiteName}-same-machine", includes: '**/reports/**, **/.maestro/screenshots/**, **/status/**, **/collected-artifacts/**, **/*.flag', allowEmpty: true

        node('built-in') {
            deleteDir()
            unstash 'source-code'
            unstash "suite-${suiteName}-same-machine"
            bat """
            cd /d "${getProjectRoot()}"
            if not exist collected-artifacts mkdir collected-artifacts
            if exist reports xcopy /E /I /Y reports collected-artifacts\\reports >nul
            if exist .maestro\\screenshots xcopy /E /I /Y .maestro\\screenshots collected-artifacts\\.maestro\\screenshots >nul
            if exist status xcopy /E /I /Y status collected-artifacts\\status >nul
            """
        }
    }
}

def runSuiteMultiAgent(String suiteName, String suiteDir) {
    node('built-in') {
        deleteDir()
        unstash 'source-code'
        def projectRoot = getProjectRoot()
        def flows = findFiles(glob: "${projectRoot}/${suiteDir}/*.yaml").collect { it.path }.sort()

        if (flows.isEmpty()) {
            echo "No flows found in ${suiteDir}. Skipping."
            return
        }

        bat """
        cd /d "${projectRoot}"
        if not exist collected-artifacts mkdir collected-artifacts
        """

        for (flow in flows) {
            def flowName = flow.tokenize('/\\\\')[-1].replace('.yaml','')
            echo "Running ${suiteName}/${flowName} in parallel across device agents"

            def branches = [:]

            branches["${flowName} - ${params.DEVICE1_ID}"] = {
                node(params.DEVICE1_LABEL) {
                    deleteDir()
                    unstash 'source-code'
                    def root = getProjectRoot()
                    catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                        bat """
                        cd /d "${root}"
                        call scripts\\run_one_flow_on_device.bat "${suiteName}" "${flowName}" "${flow}" "${params.DEVICE1_ID}" "${resolveMaestroCmd()}" "${params.APP_PACKAGE}" "${params.RETRY_FAILED}"
                        if errorlevel 1 (
                            echo 1> "${root}\\${suiteName}_${flowName}_${params.DEVICE1_ID}.failed"
                            exit /b 0
                        )
                        """
                    }
                    stash name: "artifacts-${suiteName}-${flowName}-${params.DEVICE1_ID}", includes: '**/reports/**, **/.maestro/screenshots/**, **/status/**, **/*.failed', allowEmpty: true
                }
            }

            branches["${flowName} - ${params.DEVICE2_ID}"] = {
                node(params.DEVICE2_LABEL) {
                    deleteDir()
                    unstash 'source-code'
                    def root = getProjectRoot()
                    catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                        bat """
                        cd /d "${root}"
                        call scripts\\run_one_flow_on_device.bat "${suiteName}" "${flowName}" "${flow}" "${params.DEVICE2_ID}" "${resolveMaestroCmd()}" "${params.APP_PACKAGE}" "${params.RETRY_FAILED}"
                        if errorlevel 1 (
                            echo 1> "${root}\\${suiteName}_${flowName}_${params.DEVICE2_ID}.failed"
                            exit /b 0
                        )
                        """
                    }
                    stash name: "artifacts-${suiteName}-${flowName}-${params.DEVICE2_ID}", includes: '**/reports/**, **/.maestro/screenshots/**, **/status/**, **/*.failed', allowEmpty: true
                }
            }

            parallel branches

            deleteDir()
            unstash 'source-code'
            def root = getProjectRoot()
            bat """
            cd /d "${root}"
            if not exist collected-artifacts mkdir collected-artifacts
            """

            [params.DEVICE1_ID, params.DEVICE2_ID].each { devId ->
                unstash "artifacts-${suiteName}-${flowName}-${devId}"
                bat """
                cd /d "${root}"
                if exist reports xcopy /E /I /Y reports collected-artifacts\\reports >nul
                if exist .maestro\\screenshots xcopy /E /I /Y .maestro\\screenshots collected-artifacts\\.maestro\\screenshots >nul
                if exist status xcopy /E /I /Y status collected-artifacts\\status >nul
                if exist *.failed (
                    echo Failure detected for ${suiteName} ${flowName} ${devId}
                    echo 1> pipeline_failed.flag
                )
                del /q *.failed >nul 2>&1
                """
            }
        }
    }
}

def sendSummaryEmail(String resultText) {
    def summaryHtml = ''
    try {
        def files = findFiles(glob: '**/build-summary/summary.html')
        if (files && files.length > 0) {
            summaryHtml = readFile(files[0].path)
        }
    } catch (ignored) { }

    if (!summaryHtml?.trim()) {
        summaryHtml = """<html><body>
        <h3>Kodak Smile Pipeline Summary</h3>
        <p>Result: ${resultText}</p>
        <p>Job: ${env.JOB_NAME}</p>
        <p>Build: #${env.BUILD_NUMBER}</p>
        <p>URL: <a href='${env.BUILD_URL}'>${env.BUILD_URL}</a></p>
        </body></html>"""
    }

    emailext(
        to: params.EMAIL_TO,
        subject: "[${resultText}] Kodak Smile Pipeline - ${env.JOB_NAME} #${env.BUILD_NUMBER}",
        mimeType: 'text/html',
        body: summaryHtml,
        attachmentsPattern: '**/build-summary/*, **/collected-artifacts/**, **/ai-doctor/artifacts/**'
    )
}
