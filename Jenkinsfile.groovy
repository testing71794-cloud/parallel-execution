pipeline {
    agent none

    triggers {
        cron('H 9 * * *')
    }

    options {
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        string(name: 'DEVICES_AGENT', defaultValue: 'devices')
        string(name: 'DEVICE1_ID', defaultValue: '3C1625009Q500000')
        string(name: 'DEVICE2_ID', defaultValue: '972946209807')
        choice(name: 'SUITE', choices: ['both', 'nonprinting', 'printing'])
    }

    stages {

        stage('Checkout Code') {
            agent { label 'built-in' }
            steps {
                deleteDir()
                checkout scm
                stash name: 'code', includes: '**/*'
            }
        }

        stage('Install Dependencies (Windows)') {
            agent { label 'devices' }
            steps {
                deleteDir()
                unstash 'code'
                bat '''
                if exist package.json (
                    call npm ci || call npm install
                )
                if exist ai-doctor\package.json (
                    cd ai-doctor
                    call npm ci || call npm install
                )
                '''
                stash name: 'workspace', includes: '**/*'
            }
        }

        stage('Run Flows') {
            agent { label 'devices' }
            steps {
                deleteDir()
                unstash 'workspace'
                script {
                    def suiteDir = (params.SUITE == 'printing') ? 'Printing Flow' : 'Non printing flows'
                    def flows = []

                    def output = bat(
                        script: "cd /d "%WORKSPACE%\${suiteDir}" && dir /b *.yaml",
                        returnStdout: true
                    ).trim()

                    if (output) {
                        flows = output.split("\r?\n").collect { "${suiteDir}\${it.trim()}" }
                    }

                    for (flow in flows) {
                        echo "Running ${flow} on both devices"

                        parallel(
                            "Device1": {
                                bat "maestro test \"${flow}\" --device ${params.DEVICE1_ID}"
                            },
                            "Device2": {
                                bat "maestro test \"${flow}\" --device ${params.DEVICE2_ID}"
                            }
                        )
                    }
                }
            }
        }
    }
}
