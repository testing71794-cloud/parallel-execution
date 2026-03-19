# Run Jenkins Pipeline on Your PC (Where Devices Are Connected)

Your GCP VM runs Jenkins, but **it has no USB ports**—it can't see devices. To test on physical phones, the build must run on **your Windows PC** where the devices are attached.

---

## Two Approaches

| Approach | Where Jenkins runs | Where build runs | Best for |
|---------|--------------------|------------------|----------|
| **A: Jenkins Agent** | GCP VM | Your PC (agent) | Keep central Jenkins, multiple people |
| **B: Jenkins Locally** | Your PC | Your PC | Single setup, simpler |

---

## Option A: Add Your PC as a Jenkins Agent

The GCP Jenkins stays the controller; your PC becomes a **build agent** that runs the pipeline.

### Step 1: Create Agent in Jenkins (on GCP)

1. Open **http://34.171.234.138:8080**
2. Go to **Manage Jenkins** → **Nodes**
3. Click **New Node**
4. **Name:** `local-devices` (or `india` / your label)
5. Select **Permanent Agent** → **Create**
6. Configure:
   - **Remote root directory:** `C:\JenkinsAgent` (or any folder)
   - **Labels:** `local-devices` (this is what the pipeline will use)
   - **Launch method:** **Launch agent by connecting it to the controller**
   - **Usage:** **Only build jobs with label expressions matching this node**
7. Click **Save**

### Step 2: Install Agent on Your PC

1. On the new agent page, click **agent.jar** (or the download link) to get the agent JAR, or:
2. Download from your Jenkins: **http://34.171.234.138:8080/jnlpJars/agent.jar**
3. Create a folder, e.g. `C:\JenkinsAgent`
4. Move `agent.jar` there
5. Create `run-agent.bat` in the same folder:

```batch
@echo off
cd /d C:\JenkinsAgent
java -jar agent.jar -jnlpUrl http://34.171.234.138:8080/computer/local-devices/jenkins-agent.jnlp -secret YOUR_SECRET_HERE -workDir "C:\JenkinsAgent"
pause
```

6. In Jenkins: open your agent → the **secret** is shown. Copy it and replace `YOUR_SECRET_HERE` in the batch file.
7. On your PC, ensure:
   - Java is installed (`java -version`)
   - ADB is in PATH (`adb devices`)
   - Maestro is installed (`maestro --version`)
   - Your Android devices are connected and show in `adb devices`
8. Run `run-agent.bat`—the agent connects to Jenkins.

### Step 3: Point the Pipeline to the Agent

In your Jenkinsfile, change:

```groovy
agent any
```

to:

```groovy
agent { label 'local-devices' }
```

Push the change. When you run the job, it will run on your PC.

---

## Option B: Run Jenkins on Your PC

Simpler: run Jenkins and the pipeline entirely on your machine.

### Step 1: Install on Windows

1. Java: https://adoptium.net/
2. Jenkins: https://www.jenkins.io/download/ (Windows installer)
3. Maestro: `curl -Ls "https://get.maestro.mobile.dev" | bash` (in Git Bash) or see https://maestro.mobile.dev/getting-started/installation
4. ADB: part of Android SDK, or install Platform Tools

### Step 2: Create the Pipeline Job

1. Open http://localhost:8080
2. New Item → Pipeline → name: `kodak-smile`
3. Pipeline from SCM → Git URL: `https://github.com/testing71794-cloud/kodak-Smile-with-OpenAI`
4. Branch: `*/main`
5. Script Path: `Jenkinsfile` (or the one your repo uses)
6. Save → Build Now

The build runs on your PC and sees your USB devices.

---

## Quick Fix for “0 devices”

- **GCP VM:** Cannot see USB devices → use **Agent** (Option A) or **local Jenkins** (Option B).
- **Your PC:** Ensure `adb devices` shows your phones before running the pipeline.

---

## For Multiple Locations (India, US, etc.)

Use Option A for each person:

- India person: agent labeled `india`
- US person: agent labeled `usa`

Each agent runs on their PC with their devices. The Jenkinsfile uses `agent { label 'india' }` or `agent { label 'usa' }` so the right machine runs the job.
