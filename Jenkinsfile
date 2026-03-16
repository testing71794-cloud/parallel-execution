pipeline {
    agent any

    triggers {
        cron('H 9 * * *')
    }

    stages {
        stage('Init') {
            steps {
                script { env.TEST_EXIT_CODE = '0' }
            }
        }

        stage('Checkout From Git') {
            steps {
                git url: 'https://github.com/testing71794-cloud/kodak-Smile-with-OpenAI.git', branch: 'main'
            }
        }

        stage('Check Workspace') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'echo "Workspace: $PWD" && ls -la'
                    } else {
                        bat 'echo Current workspace: %CD% && dir'
                    }
                }
            }
        }

        stage('Check Connected Devices') {
            steps {
                script {
                    if (isUnix()) {
                        sh 'adb devices && maestro --version && node --version && npm --version'
                    } else {
                        bat 'adb devices && maestro --version && node --version && npm --version'
                    }
                }
            }
        }

        stage('Install AI Doctor Dependencies') {
            steps {
                dir('ai-doctor') {
                    script {
                        if (isUnix()) {
                            sh 'npm ci 2>/dev/null || npm install'
                        } else {
                            bat 'if exist package-lock.json (npm ci) else (npm install)'
                        }
                    }
                }
            }
        }

        stage('Run All Flows in Parallel') {
            steps {
                script {
                    def code
                    if (isUnix()) {
                        code = sh(script: 'export PROJECT_ROOT="$PWD" && chmod +x scripts/run_all_parallel.sh && ./scripts/run_all_parallel.sh', returnStatus: true)
                    } else {
                        code = bat(script: 'set PROJECT_ROOT=%CD% && call scripts\\run_all_parallel.bat', returnStatus: true)
                    }
                    env.TEST_EXIT_CODE = "${code}"
                    echo "Maestro exit code: ${code}"
                }
            }
        }

        stage('Run AI Doctor On Failure') {
            when {
                expression { env.TEST_EXIT_CODE != '0' }
            }
            steps {
                dir('ai-doctor') {
                    script {
                        if (isUnix()) {
                            sh 'node index.mjs'
                        } else {
                            bat 'node index.mjs'
                        }
                    }
                }
            }
        }

        stage('Archive Artifacts') {
            steps {
                archiveArtifacts artifacts: '.maestro/**/*, reports/**/*, report.xml, report_retry.xml, ai-doctor/artifacts/**/*', allowEmptyArchive: true
            }
        }
    }

    post {
        always {
            echo 'Pipeline finished.'
        }

        success {
            script {
                if (env.TEST_EXIT_CODE == '0') {
                    echo 'All flows (Non-printing + Printing) completed successfully.'
                }
            }
        }

        unsuccessful {
            script {
                if (env.TEST_EXIT_CODE != '0') {
                    error('Tests failed. AI Doctor executed and artifacts were archived.')
                }
            }
        }
    }
}