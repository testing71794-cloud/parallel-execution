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
        string(name: 'DEVICES_AGENT', defaultValue: 'devices', description: 'Agent label for same-machine execution.')
        string(name: 'DEVICE1_LABEL', defaultValue: 'device-agent-1', description: 'Agent label for device 1 in multi-agent mode.')
        string(name: 'DEVICE2_LABEL', defaultValue: 'device-agent-2', description: 'Agent label for device 2 in multi-agent mode.')
        string(name: 'DEVICE1_ID', defaultValue: '3C1625009Q500000', description: 'ADB device ID for device 1.')
        string(name: 'DEVICE2_ID', defaultValue: 'RZCWA2B05RB', description: 'ADB device ID for device 2.')
        choice(name: 'RUN_MODE', choices: ['multi_agent_parallel', 'same_machine_parallel'], description: 'multi_agent_parallel is recommended. same_machine_parallel runs both devices from one PC.')
        choice(name: 'SUITE', choices: ['both', 'nonprinting', 'printing'], description: 'Which suites to run.')
        booleanParam(name: 'AI_ANALYSIS', defaultValue: true, description: 'Run AI analysis when failures exist.')
        booleanParam(name: 'RETRY_FAILED', defaultValue: true, description: 'Retry failed flow once.')
        choice(name: 'SEND_EMAIL_MODE', choices: ['failed_only', 'always', 'never'], description: 'When to send summary email.')
        string(name: 'MAESTRO_CMD', defaultValue: '', description: 'Optional Maestro override path.')
        string(name: 'APP_PACKAGE', defaultValue: 'com.kodaksmile', description: 'App package for validation.')
        string(name: 'EMAIL_TO', defaultValue: 'your-email@example.com', description: 'Summary email recipient(s).')
        string(name: 'PROJECT_SUBDIR', defaultValue: '', description: 'Optional repo subfolder if project is not at workspace root.')
    }

    stages {
        stage('Fetch Code from GitHub') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                checkout scm
                stash name: 'source-code', includes: '**/*'
            }
        }

        stage('Install Dependencies') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'source-code'
                script {
                    def projectRoot = getProjectRoot()
                    bat """
                    cd /d "${projectRoot}"
                    if exist package.json (
                        call npm ci || call npm install
                    )
                    if exist ai-doctor\\package.json (
                        cd ai-doctor
                        call npm ci || call npm install
                    )
                    """
                }
                stash name: 'workspace-with-deps', includes: '**/*', allowEmpty: true
            }
        }

        stage('Execute Non Printing Flows') {
            when { expression { params.SUITE in ['both', 'nonprinting'] } }
            agent { label 'built-in' }
            steps {
                script {
                    if (params.RUN_MODE == 'multi_agent_parallel') {
                        runSuiteMultiAgent('nonprinting', 'Non printing flows')
                    } else {
                        runSuiteSameMachineParallel('nonprinting', 'Non printing flows')
                    }
                }
            }
        }

        stage('Generate Excel Report for Non Printing') {
            when { expression { params.SUITE in ['both', 'nonprinting'] } }
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'workspace-with-deps'
                script {
                    def projectRoot = getProjectRoot()
                    bat """
                    cd /d "${projectRoot}"
                    python scripts\\generate_excel_report.py status reports\\nonprinting_summary nonprinting
                    """
                }
                stash name: 'nonprinting-report', includes: '**/reports/nonprinting_summary/**', allowEmpty: true
            }
        }

        stage('Execute Printing Flows') {
            when { expression { params.SUITE in ['both', 'printing'] } }
            agent { label 'built-in' }
            steps {
                script {
                    if (params.RUN_MODE == 'multi_agent_parallel') {
                        runSuiteMultiAgent('printing', 'Printing Flow')
                    } else {
                        runSuiteSameMachineParallel('printing', 'Printing Flow')
                    }
                }
            }
        }

        stage('Generate Excel Report for Printing') {
            when { expression { params.SUITE in ['both', 'printing'] } }
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'workspace-with-deps'
                script {
                    def projectRoot = getProjectRoot()
                    bat """
                    cd /d "${projectRoot}"
                    python scripts\\generate_excel_report.py status reports\\printing_summary printing
                    """
                }
                stash name: 'printing-report', includes: '**/reports/printing_summary/**', allowEmpty: true
            }
        }

        stage('AI Failure Analysis + Smart Retry') {
            when { expression { params.AI_ANALYSIS } }
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'workspace-with-deps'
                script {
                    def projectRoot = getProjectRoot()
                    if (fileExists("${projectRoot}/pipeline_failed.flag")) {
                        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                            bat """
                            cd /d "${projectRoot}"
                            call scripts\\run_ai_analysis.bat
                            if errorlevel 1 (
                                echo 1> ai_failed.flag
                                exit /b 0
                            )
                            """
                        }
                    } else {
                        echo "No failures found. Skipping AI analysis."
                    }
                }
            }
        }

        stage('Archive Reports & Artifacts') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'workspace-with-deps'
                script {
                    def projectRoot = getProjectRoot()
                    bat """
                    cd /d "${projectRoot}"
                    if not exist build-summary mkdir build-summary
                    python scripts\\generate_build_summary.py collected-artifacts build-summary
                    """
                }
            }
            post {
                always {
                    archiveArtifacts artifacts: '**/reports/**, **/.maestro/screenshots/**, **/status/**, **/collected-artifacts/**, **/build-summary/**, **/ai-doctor/artifacts/**, **/*.flag', allowEmptyArchive: true
                }
            }
        }

        stage('Finalize Build Result') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                unstash 'workspace-with-deps'
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

                    echo "pipeline_failed = ${pipelineFailed}"
                    echo "ai_failed = ${aiFailed}"
                    echo "Final result = ${currentBuild.result}"
                }
            }
        }
    }

    post {
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

def runSuiteSameMachineParallel(String suiteName, String suiteDir) {
    node(params.DEVICES_AGENT) {
        deleteDir()
        unstash 'workspace-with-deps'
        def projectRoot = getProjectRoot()

        catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
            bat """
            cd /d "${projectRoot}"
            call scripts\\precheck_environment.bat "${resolveMaestroCmd()}" "${params.APP_PACKAGE}"
            if not exist collected-artifacts mkdir collected-artifacts
            call scripts\\run_suite_parallel_same_machine.bat "${suiteName}" "${suiteDir}" "${params.DEVICE1_ID}" "${params.DEVICE2_ID}" "${resolveMaestroCmd()}" "${params.APP_PACKAGE}" "${params.RETRY_FAILED}"
            if errorlevel 1 (
                echo 1> pipeline_failed.flag
                exit /b 0
            )
            """
        }

        stash name: "suite-${suiteName}-same-machine-parallel", includes: '**/reports/**, **/.maestro/screenshots/**, **/status/**, **/collected-artifacts/**, **/*.flag', allowEmpty: true

        node('built-in') {
            deleteDir()
            unstash 'workspace-with-deps'
            unstash "suite-${suiteName}-same-machine-parallel"
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
        unstash 'workspace-with-deps'
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
            echo "Running ${flowName} on both devices in parallel. Pipeline will continue even if one branch fails."

            def branches = [:]

            branches["${flowName} - ${params.DEVICE1_ID}"] = {
                node(params.DEVICE1_LABEL) {
                    deleteDir()
                    unstash 'workspace-with-deps'
                    def root = getProjectRoot()
                    catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                        bat """
                        cd /d "${root}"
                        call scripts\\precheck_environment.bat "${resolveMaestroCmd()}" "${params.APP_PACKAGE}" "${params.DEVICE1_ID}"
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
                    unstash 'workspace-with-deps'
                    def root = getProjectRoot()
                    catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                        bat """
                        cd /d "${root}"
                        call scripts\\precheck_environment.bat "${resolveMaestroCmd()}" "${params.APP_PACKAGE}" "${params.DEVICE2_ID}"
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
            unstash 'workspace-with-deps'
            bat """
            cd /d "${projectRoot}"
            if not exist collected-artifacts mkdir collected-artifacts
            """

            [params.DEVICE1_ID, params.DEVICE2_ID].each { devId ->
                unstash "artifacts-${suiteName}-${flowName}-${devId}"
                bat """
                cd /d "${projectRoot}"
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
