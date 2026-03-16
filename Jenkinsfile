pipeline {
    agent any

    environment {
        MAESTRO_PATH = "/var/lib/jenkins/.maestro/bin"
        ADB_PATH = "/usr/bin/adb"
    }

    triggers {
        githubPush()
    }

    stages {

        stage('Checkout Code') {
            steps {
                git url: 'https://github.com/testing71794-cloud/kodak-Smile-with-OpenAI.git', branch: 'main'
            }
        }

        stage('Check Environment') {
            steps {
                sh '''
                echo "Checking environment..."
                $ADB_PATH devices
                node -v
                npm -v
                $MAESTRO_PATH/maestro --version
                '''
            }
        }

        stage('Detect Devices') {
            steps {
                sh '''
                echo "Connected devices:"
                $ADB_PATH devices
                '''
            }
        }

        stage('Run Non Printing Tests') {
            steps {
                sh '''
                export PATH=$PATH:$MAESTRO_PATH
                maestro test "Non printing flows"
                '''
            }
        }

        stage('Run Printing Tests') {
            steps {
                sh '''
                export PATH=$PATH:$MAESTRO_PATH
                maestro test "Printing Flow"
                '''
            }
        }

        stage('Generate Report') {
            steps {
                sh '''
                echo "Generating report..."
                ls -la .maestro || true
                '''
            }
        }

        stage('Archive Results') {
            steps {
                archiveArtifacts artifacts: '.maestro/**/*', allowEmptyArchive: true
            }
        }
    }

    post {

        success {
            echo 'All tests passed successfully!'
        }

        failure {
            mail to: 'kodaksmilechina@gmail.com',
                 subject: "❌ Jenkins Build Failed - ${env.JOB_NAME}",
                 body: """
                 Maestro tests failed.

                 Job: ${env.JOB_NAME}
                 Build: ${env.BUILD_NUMBER}

                 Check details:
                 ${env.BUILD_URL}
                 """
        }
    }
}         