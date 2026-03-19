# Jenkins Setup – Do This (Step by Step)

I cannot access your Jenkins UI. Follow these steps **yourself** to enable the hybrid setup (server + your PC with devices).

---

## Part 1: Add label "built-in" to your server node

1. Open **http://34.171.234.138:8080**
2. Go to **Manage Jenkins** → **Nodes**
3. Click your server node (often named **built-in** or **master**)
4. Click **Configure**
5. In **Labels**, add: `built-in` (keep any existing labels)
6. Click **Save**

---

## Part 2: Create the "devices" agent (your PC)

1. Go to **Manage Jenkins** → **Nodes**
2. Click **New Node**
3. **Node name:** `my-pc-devices`
4. Select **Permanent Agent** → **OK**
5. Configure:
   - **Remote root directory:** `C:\JenkinsAgent`
   - **Labels:** `devices`
   - **# of executors:** `1`
   - **Launch method:** **Launch agent by connecting it to the controller**
6. Click **Save**

---

## Part 3: Get the agent command

1. Click the new agent **my-pc-devices**
2. You will see something like:
   ```
   Run from agent command line:
   java -jar agent.jar -url http://34.171.234.138:8080/ -secret xxxxx -name my-pc-devices -workDir "C:\JenkinsAgent"
   ```
3. Or use the **agent.jar** download link on that page

---

## Part 4: Run the agent on your PC

1. Create folder `C:\JenkinsAgent`
2. Download **agent.jar** from: `http://34.171.234.138:8080/jnlpJars/agent.jar`
3. Put `agent.jar` in `C:\JenkinsAgent`
4. Open **Command Prompt** or **PowerShell** and run:
   ```cmd
   cd C:\JenkinsAgent
   java -jar agent.jar -url http://34.171.234.138:8080/ -secret YOUR_SECRET -name my-pc-devices -workDir "C:\JenkinsAgent"
   ```
   (Replace `YOUR_SECRET` with the secret from the agent page.)
5. Keep this window open while using Jenkins.

---

## Part 5: Point your job to Jenkinsfile.hybrid

1. Open your pipeline job (e.g. **Kodak-smile-automation**)
2. Click **Configure**
3. Under **Pipeline**, find **Script Path**
4. Change to: `Jenkinsfile.hybrid`
5. Click **Save**

---

## Part 6: On your PC – prerequisites

Before running a build, ensure on your PC:

- **Java:** `java -version`
- **ADB:** `adb devices` (your phones listed)
- **Maestro:** `maestro --version`
- **Node.js:** `node -v` (optional for some steps)

---

## After setup

1. Click **Build Now**
2. First stages run on the server (Checkout, Install)
3. Pipeline waits for your PC agent
4. Start the agent (Part 4) – build continues
5. Maestro runs on your PC using your USB devices
6. Final stages run again on the server (AI Doctor, Archive)

---

## Quick reference

| What | Where | Action |
|------|-------|--------|
| Jenkins UI | http://34.171.234.138:8080 | You configure |
| Agent on PC | C:\JenkinsAgent | Run `java -jar agent.jar ...` |
| Script Path | Job config | `Jenkinsfile.hybrid` |
