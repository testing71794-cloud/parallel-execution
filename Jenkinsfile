pipeline {
    agent { label 'devices' }

    triggers {
        cron('H 9 * * *')
    }

    stages {
        stage('Run Sequential Pipeline') {
            steps {
                bat 'scripts\\run_all_flows_pipeline.bat'
            }
        }
    }

    post {
        failure {
            mail to: 'your-email@example.com',
                 subject: "Kodak Smile Pipeline FAILED",
                 body: "Pipeline failed. Check Jenkins logs."
        }
    }
}
