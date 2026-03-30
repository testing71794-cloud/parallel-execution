pipeline {
    agent none

    triggers {
        cron('H 9 * * *')
    }

    options {
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        skipDefaultCheckout(true)
    }

    parameters {
        string(name: 'DEVICES_AGENT', defaultValue: 'devices', description: 'Windows Jenkins node label that has ADB, Maestro, Python and Node installed.')
        string(name: 'APP_PACKAGE', defaultValue: 'com.kodaksmile', description: 'Android app package checked during precheck.')
        string(name: 'MAESTRO_CMD', defaultValue: '', description: 'Optional full path to Maestro executable. Leave blank to use PATH or C:\\maestro\\bin\\maestro.exe.')
        booleanParam(name: 'RUN_NON_PRINTING', defaultValue: true, description: 'Run flows from Non printing flows folder.')
        booleanParam(name: 'RUN_PRINTING', defaultValue: true, description: 'Run flows from Printing Flow folder.')
        booleanParam(name: 'RETRY_FAILED', defaultValue: true, description: 'Retry failed flows once on the same device.')
        booleanParam(name: 'RUN_AI_ANALYSIS', defaultValue: true, description: 'Run AI doctor only when failures are detected.')
        booleanParam(name: 'SEND_FINAL_EMAIL', defaultValue: true, description: 'Send one end-of-run email with the Excel reports and AI analysis artifacts.')
    }

    stages {
        stage('Fetch Code from GitHub') {
            agent { label 'built-in' }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
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
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation

                    if exist reports rmdir /s /q reports
                    if exist status rmdir /s /q status
                    if exist collected-artifacts rmdir /s /q collected-artifacts
                    if exist build-summary rmdir /s /q build-summary
                    if exist .maestro rmdir /s /q .maestro
                    if exist temp-runners rmdir /s /q temp-runners
                    if exist ai-doctor\\artifacts rmdir /s /q ai-doctor\\artifacts
                    del /q detected_devices.txt 2>nul
                    del /q *.flag 2>nul
                    del /q *.failed 2>nul

                    python -m pip install --upgrade pip || (echo 1> install_failed.flag & exit /b 1)
                    python -m pip install -r scripts\\requirements-python.txt || (echo 1> install_failed.flag & exit /b 1)

                    if exist package.json (
                        call npm ci || call npm install || (echo 1> install_failed.flag & exit /b 1)
                    )

                    if exist ai-doctor\\package.json (
                        cd ai-doctor
                        call npm ci || call npm install || (echo 1> ..\\install_failed.flag & exit /b 1)
                        cd ..
                    )
                    '''
                }
            }
        }

        stage('Environment Precheck') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    call scripts\\precheck_environment.bat "''' + params.MAESTRO_CMD + '''" "''' + params.APP_PACKAGE + '''" || (echo 1> precheck_failed.flag & exit /b 1)
                    '''
                }
            }
        }

        stage('Debug Runner Files') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation

                    echo ===== WORKSPACE =====
                    cd

                    echo ===== SCRIPTS =====
                    dir scripts

                    echo ===== TEMP RUNNERS =====
                    dir temp-runners

                    echo ===== NON PRINTING LOGS =====
                    dir reports\\nonprinting\\logs

                    echo ===== STATUS =====
                    dir status

                    echo ===== FIND IN BAT =====
                    findstr /i /n "temp-runners run_one_flow_on_device logs results status" scripts\\run_suite_parallel_same_machine.bat

                    echo ===== FIND IN PS1 =====
                    findstr /i /n "temp-runners run_one_flow_on_device logs results status" scripts\\run_suite_parallel_same_machine.ps1

                    echo ===== RUN ONE FLOW FILE =====
                    type scripts\\run_one_flow_on_device.bat
                    '''
                }
            }
        }

        stage('Manual Single Device Test') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation

                    call scripts\\run_one_flow_on_device.bat nonprinting "C:\\JenkinsAgent\\workspace\\Kodak-smile-automation\\Non printing flows\\flow1.yaml" flow1 RZCT415WSSW com.kodaksmile true __EMPTY__ __EMPTY__

                    echo ===== AFTER RUN LOGS =====
                    dir reports\\nonprinting\\logs

                    echo ===== AFTER RUN RESULTS =====
                    dir reports\\nonprinting\\results

                    echo ===== AFTER RUN STATUS =====
                    dir status
                    '''
                }
            }
        }

        stage('Detect Connected Devices') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    call scripts\\list_devices.bat || (echo 1> device_detection_failed.flag & exit /b 1)
                    '''
                }
            }
        }

        stage('Execute Non Printing Flows') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    call scripts\\run_suite_parallel_same_machine.bat nonprinting "Non printing flows" "''' + params.MAESTRO_CMD + '''" "''' + params.APP_PACKAGE + '''" "''' + params.RETRY_FAILED.toString() + '''" || (echo 1> nonprinting_failed.flag & exit /b 1)
                    '''
                }
            }
        }

        stage('Generate Excel Report for Non Printing') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    python scripts\\generate_excel_report.py status reports\\nonprinting_summary nonprinting || (echo 1> nonprinting_report_failed.flag & exit /b 1)
                    '''
                }
            }
        }

        stage('Execute Printing Flows on Physical Devices') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    call scripts\\run_suite_parallel_same_machine.bat printing "Printing Flow" "''' + params.MAESTRO_CMD + '''" "''' + params.APP_PACKAGE + '''" "''' + params.RETRY_FAILED.toString() + '''" || (echo 1> printing_failed.flag & exit /b 1)
                    '''
                }
            }
        }

        stage('Generate Excel Report for Printing') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    python scripts\\generate_excel_report.py status reports\\printing_summary printing || (echo 1> printing_report_failed.flag & exit /b 1)
                    '''
                }
            }
        }

        stage('AI Failure Analysis + Smart Retry') {
            when { expression { return params.RUN_AI_ANALYSIS } }
            agent { label params.DEVICES_AGENT }
            steps {
                script {
                    if (fileExists('pipeline_failed.flag')) {
                        catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                            bat '''
                            cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                            call scripts\\run_ai_analysis.bat || (echo 1> ai_failed.flag & exit /b 1)
                            '''
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
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    python scripts\\generate_build_summary.py collected-artifacts build-summary || (echo 1> summary_failed.flag & exit /b 1)
                    '''
                }
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    if exist scripts\\generate_final_report.py (
                        python scripts\\generate_final_report.py . status build-summary\\final_execution_report.xlsx || (echo 1>> summary_failed.flag & exit /b 1)
                    ) else (
                        echo generate_final_report.py not found. Skipping final report generation.
                    )
                    '''
                }
            }
        }

        stage('Send Final Email') {
            when { expression { return params.SEND_FINAL_EMAIL } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat '''
                    cd /d C:\\JenkinsAgent\\workspace\\Kodak-smile-automation
                    if exist scripts\\send_execution_email.py (
                        python scripts\\send_execution_email.py || (echo 1> email_failed.flag & exit /b 1)
                    ) else (
                        echo send_execution_email.py not found. Skipping email step.
                    )
                    '''
                }
            }
        }

        stage('Archive Reports & Artifacts') {
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
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
                        'printing_failed.flag'
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