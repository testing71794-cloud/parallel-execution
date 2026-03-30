pipeline {
    agent none

    parameters {
        choice(
            name: 'DEVICES_AGENT',
            choices: ['devices', 'built-in'],
            description: 'devices = your PC with USB phones'
        )
        string(name: 'APP_PACKAGE', defaultValue: 'com.kodaksmile', description: 'App package id for Maestro/app launch checks')
        string(name: 'MAESTRO_CMD', defaultValue: 'maestro', description: 'Maestro command to use')
        string(name: 'JAVA_HOME_OVERRIDE', defaultValue: '', description: 'Optional JAVA_HOME override on device node')
        booleanParam(name: 'RUN_NON_PRINTING', defaultValue: true, description: 'Run non-printing flows')
        booleanParam(name: 'RUN_PRINTING', defaultValue: true, description: 'Run printing flows')
        booleanParam(name: 'RUN_AI_ANALYSIS', defaultValue: true, description: 'Run AI analysis when failures happen')
        booleanParam(name: 'SEND_FINAL_EMAIL', defaultValue: false, description: 'Send final summary email')
        booleanParam(name: 'CLEAR_STATE', defaultValue: true, description: 'Reserved for flow runner; do not map RETRY here')
        booleanParam(name: 'RETRY_FAILED', defaultValue: false, description: 'Reserved for future retry logic only')
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

                    if exist reports rmdir /s /q reports
                    if exist status rmdir /s /q status
                    if exist collected-artifacts rmdir /s /q collected-artifacts
                    if exist build-summary rmdir /s /q build-summary
                    if exist .maestro rmdir /s /q .maestro
                    if exist temp-runners rmdir /s /q temp-runners
                    if exist ai-doctor/artifacts rmdir /s /q ai-doctor/artifacts
                    del /q detected_devices.txt 2>nul
                    del /q *.flag 2>nul
                    del /q *.failed 2>nul

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

        stage('Environment Precheck') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    script {
                        def envList = []
                        if (params.JAVA_HOME_OVERRIDE?.trim()) {
                            envList << "JAVA_HOME_OVERRIDE=${params.JAVA_HOME_OVERRIDE}"
                        }
                        withEnv(envList) {
                            bat """
                            cd /d "${env.WORKSPACE}"
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
                    bat """
                    cd /d "${env.WORKSPACE}"
                    call scripts/list_devices.bat || (echo 1> device_detection_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    """
                }
            }
        }

        stage('Execute Non Printing Flows') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    script {
                        def envList = []
                        if (params.JAVA_HOME_OVERRIDE?.trim()) {
                            envList << "JAVA_HOME_OVERRIDE=${params.JAVA_HOME_OVERRIDE}"
                        }
                        withEnv(envList) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            call scripts/run_suite_parallel_same_machine.bat nonprinting "Non printing flows" "" "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" || (echo 1> nonprinting_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                            """
                        }
                    }
                }
            }
        }

        stage('Validate Non Printing Artifacts') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    if not exist status\\nonprinting__*.txt (echo 1> nonprinting_no_results.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    if not exist reports\\nonprinting\\results\\*.csv (echo 1> nonprinting_no_results.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    if not exist reports\\nonprinting\\logs\\*.log (echo 1> nonprinting_no_results.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    """
                }
            }
        }

        stage('Generate Excel Report for Non Printing') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/generate_excel_report.py status reports/nonprinting_summary nonprinting || (echo 1> nonprinting_report_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    """
                }
            }
        }

        stage('Execute Printing Flows on Physical Devices') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    script {
                        def envList = []
                        if (params.JAVA_HOME_OVERRIDE?.trim()) {
                            envList << "JAVA_HOME_OVERRIDE=${params.JAVA_HOME_OVERRIDE}"
                        }
                        withEnv(envList) {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            call scripts/run_suite_parallel_same_machine.bat printing "Printing Flow" "" "${params.APP_PACKAGE}" "${params.CLEAR_STATE.toString()}" "${params.MAESTRO_CMD}" || (echo 1> printing_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                            """
                        }
                    }
                }
            }
        }

        stage('Validate Printing Artifacts') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    if not exist status\\printing__*.txt (echo 1> printing_no_results.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    if not exist reports\\printing\\results\\*.csv (echo 1> printing_no_results.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    if not exist reports\\printing\\logs\\*.log (echo 1> printing_no_results.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    """
                }
            }
        }

        stage('Generate Excel Report for Printing') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/generate_excel_report.py status reports/printing_summary printing || (echo 1> printing_report_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    """
                }
            }
        }

        stage('AI Failure Analysis + Smart Retry') {
            when { expression { return params.RUN_AI_ANALYSIS } }
            agent { label params.DEVICES_AGENT }
            steps {
                script {
                    if (fileExists('pipeline_failed.flag')) {
                        catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                            bat """
                            cd /d "${env.WORKSPACE}"
                            call scripts/run_ai_analysis.bat || (echo 1> ai_failed.flag & exit /b 1)
                            """
                        }
                    } else {
                        echo 'No failures detected. Skipping AI analysis.'
                    }
                }
            }
        }

        stage('Build Summary') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    python scripts/generate_build_summary.py status build-summary || (echo 1> summary_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    if exist scripts/generate_final_report.py (
                        python scripts/generate_final_report.py . status build-summary/final_execution_report.xlsx || (echo 1>> summary_failed.flag & echo 1> pipeline_failed.flag & exit /b 1)
                    ) else (
                        echo generate_final_report.py not found. Skipping final report generation.
                    )
                    """
                }
            }
        }

        stage('Send Final Email') {
            when { expression { return params.SEND_FINAL_EMAIL } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                    bat """
                    cd /d "${env.WORKSPACE}"
                    if exist scripts/send_execution_email.py (
                        python scripts/send_execution_email.py || (echo 1> email_failed.flag & exit /b 1)
                    ) else (
                        echo send_execution_email.py not found. Skipping email step.
                    )
                    """
                }
            }
        }

        stage('Archive Reports & Artifacts') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'UNSTABLE', stageResult: 'UNSTABLE') {
                    archiveArtifacts artifacts: 'reports/**, status/**, collected-artifacts/**, build-summary/**, .maestro/screenshots/**, ai-doctor/artifacts/**, detected_devices.txt, *.flag, *.failed', allowEmptyArchive: true
                }
            }
        }

        stage('Finalize Build Result') {
            agent { label params.DEVICES_AGENT }
            steps {
                script {
                    def hardFailureFlags = [
                        'pipeline_failed.flag',
                        'install_failed.flag',
                        'precheck_failed.flag',
                        'device_detection_failed.flag',
                        'nonprinting_failed.flag',
                        'printing_failed.flag',
                        'nonprinting_no_results.flag',
                        'printing_no_results.flag'
                    ]

                    def unstableFlags = [
                        'nonprinting_report_failed.flag',
                        'printing_report_failed.flag',
                        'summary_failed.flag',
                        'ai_failed.flag',
                        'email_failed.flag'
                    ]

                    def hardFailures = hardFailureFlags.findAll { fileExists(it) }
                    def unstableIssues = unstableFlags.findAll { fileExists(it) }

                    if (!hardFailures.isEmpty()) {
                        currentBuild.result = 'FAILURE'
                        echo 'Final result: FAILURE'
                        echo 'Hard failure flags: ' + hardFailures.join(', ')
                    } else if (!unstableIssues.isEmpty() || currentBuild.currentResult == 'UNSTABLE') {
                        currentBuild.result = 'UNSTABLE'
                        echo 'Final result: UNSTABLE'
                        echo 'Unstable flags: ' + unstableIssues.join(', ')
                    } else {
                        currentBuild.result = 'SUCCESS'
                        echo 'Final result: SUCCESS'
                    }
                }
            }
        }
    }

    post {
        always {
            echo "Build finished with status: ${currentBuild.currentResult}"
        }
    }
}