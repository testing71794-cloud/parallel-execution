pipeline {
    agent any

    parameters {
        booleanParam(
            name: 'SEND_FINAL_EMAIL',
            defaultValue: true,
            description: 'In case of email: when enabled, run Send Final Email (replace YOUR_APP_PASSWORD_HERE in that stage)'
        )
    }

    stages {

        stage('Dummy Test Stage') {
            steps {
                bat '''
                echo Running your pipeline...
                '''
            }
        }

        stage('Send Final Email') {
            when { expression { return params.SEND_FINAL_EMAIL } }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'UNSTABLE') {
                    bat '''
                    cd /d "%WORKSPACE%"

                    echo ==============================
                    echo SIMPLE EMAIL MODE
                    echo ==============================

                    set SMTP_SERVER=smtp.gmail.com
                    set SMTP_HOST=smtp.gmail.com
                    set SMTP_PORT=587
                    set SMTP_USER=kodaksmilechina@gmail.com
                    set SMTP_PASS=YOUR_APP_PASSWORD_HERE
                    set RECEIVER_EMAIL=kodaksmilechina@gmail.com
                    set MAIL_TO=kodaksmilechina@gmail.com
                    set PYTHONIOENCODING=utf-8
                    set ORCH_EMAIL_STRICT=1
                    set "FINAL_EXECUTION_REPORT_XLSX=%WORKSPACE%\final_execution_report.xlsx"

                    echo DEBUG:
                    echo SMTP_USER=%SMTP_USER%
                    echo SMTP_SERVER=%SMTP_SERVER%
                    echo RECEIVER_EMAIL=%RECEIVER_EMAIL%

                    echo Running email script...
                    python mailout\\send_email.py || (echo 1>email_failed.flag)

                    echo ==============================
                    echo EMAIL COMPLETED
                    echo ==============================
                    '''
                }
            }
        }
    }
}
