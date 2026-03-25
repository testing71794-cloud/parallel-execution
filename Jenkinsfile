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
    }

    stages {
        stage('Fetch Code from GitHub') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                checkout scm
                stash name: 'repo', includes: '**/*', useDefaultExcludes: false
            }
        }

        stage('Install Dependencies') {
            agent { label params.DEVICES_AGENT }
            steps {
                deleteDir()
                unstash 'repo'
                bat '''
                if exist reports rmdir /s /q reports
                if exist status rmdir /s /q status
                if exist collected-artifacts rmdir /s /q collected-artifacts
                if exist build-summary rmdir /s /q build-summary
                if exist .maestro rmdir /s /q .maestro
                if exist temp-runners rmdir /s /q temp-runners
                del /q *.flag 2>nul
                del /q *.failed 2>nul

                python -m pip install --upgrade pip
                python -m pip install -r scripts\requirements-python.txt

                if exist package.json (
                    call npm ci || call npm install
                )

                if exist ai-doctor\package.json (
                    cd ai-doctor
                    call npm ci || call npm install
                    cd ..
                )
                '''
            }
        }

        stage('Environment Precheck') {
            agent { label params.DEVICES_AGENT }
            steps {
                bat 'call scripts\\precheck_environment.bat "' + params.MAESTRO_CMD + '" "' + params.APP_PACKAGE + '"'
            }
        }

        stage('Detect Connected Devices') {
            agent { label params.DEVICES_AGENT }
            steps {
                bat 'call scripts\\list_devices.bat'
            }
        }

        stage('Execute Non Printing Flows') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat 'call scripts\\run_suite_parallel_same_machine.bat nonprinting "Non printing flows" "' + params.MAESTRO_CMD + '" "' + params.APP_PACKAGE + '" "' + params.RETRY_FAILED.toString() + '"'
                }
            }
        }

        stage('Generate Excel Report for Non Printing') {
            when { expression { return params.RUN_NON_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                bat 'python scripts\\generate_excel_report.py status reports\\nonprinting_summary nonprinting'
            }
        }

        stage('Execute Printing Flows on Physical Devices') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    bat 'call scripts\\run_suite_parallel_same_machine.bat printing "Printing Flow" "' + params.MAESTRO_CMD + '" "' + params.APP_PACKAGE + '" "' + params.RETRY_FAILED.toString() + '"'
                }
            }
        }

        stage('Generate Excel Report for Printing') {
            when { expression { return params.RUN_PRINTING } }
            agent { label params.DEVICES_AGENT }
            steps {
                bat 'python scripts\\generate_excel_report.py status reports\\printing_summary printing'
            }
        }

        stage('AI Failure Analysis + Smart Retry') {
            when { expression { return params.RUN_AI_ANALYSIS } }
            agent { label params.DEVICES_AGENT }
            steps {
                script {
                    if (fileExists('pipeline_failed.flag')) {
                        catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                            bat 'call scripts\\run_ai_analysis.bat'
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
                bat 'python scripts\\generate_build_summary.py collected-artifacts build-summary'
            }
        }

        stage('Archive Reports & Artifacts') {
            agent { label params.DEVICES_AGENT }
            steps {
                archiveArtifacts artifacts: 'reports/**, status/**, collected-artifacts/**, build-summary/**, .maestro/screenshots/**, ai-doctor/artifacts/**, detected_devices.txt, *.flag, *.failed', allowEmptyArchive: true
            }
        }

        stage('Finalize Build Result') {
            agent { label params.DEVICES_AGENT }
            steps {
                script {
                    def hasFailures = fileExists('pipeline_failed.flag')
                    if (hasFailures) {
                        currentBuild.result = 'FAILURE'
                        echo 'Final result: FAILURE'
                    } else if (currentBuild.currentResult == 'UNSTABLE') {
                        currentBuild.result = 'UNSTABLE'
                        echo 'Final result: UNSTABLE'
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
