pipeline {
    agent any

    triggers {
        cron('H 9 * * *')
    }

    environment {
        TEST_EXIT_CODE = '0'
        TEST_SUITE = 'tests'
    }

    stages {
        stage('Checkout From Git') {
            steps {
                checkout scm
            }
        }

        stage('Check Workspace') {
            steps {
                bat 'echo Current workspace: %CD%'
                bat 'dir'
            }
        }

        stage('Check Connected Devices') {
            steps {
                bat 'adb devices'
                bat 'maestro --version'
                bat 'node --version'
                bat 'npm --version'
            }
        }

        stage('Install AI Doctor Dependencies') {
            steps {
                dir('ai-doctor') {
                    bat 'if exist package-lock.json (npm ci) else (npm install)'
                }
            }
        }

        stage('Run Non Printing Flows in Parallel') {
            steps {
                script {
                    def code = bat(
                        script: 'maestro test "%TEST_SUITE%" --shard-all',
                        returnStatus: true
                    )
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
                    bat 'node index.mjs'
                }
            }
        }

        stage('Archive Artifacts') {
            steps {
                archiveArtifacts artifacts: '.maestro/**/*, reports/**/*, ai-doctor/artifacts/**/*', allowEmptyArchive: true
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
                    echo 'Non-printing scheduled automation completed successfully.'
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