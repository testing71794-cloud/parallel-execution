import "dotenv/config";
import nodemailer from "nodemailer";

export function isEmailConfigured() {
  return Boolean(
    process.env.FAIL_EMAIL_TO &&
      process.env.SMTP_HOST &&
      process.env.SMTP_PORT &&
      process.env.SMTP_USER &&
      process.env.SMTP_PASS
  );
}

/**
 * Sends email and returns nodemailer "info".
 * Supports HTML + attachments (screenshots).
 */
export async function sendFailureEmail({ subject, text, html, attachments = [] }) {
  if (!isEmailConfigured()) {
    throw new Error(
      "Email not configured. Required: FAIL_EMAIL_TO, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS (optional: SMTP_FROM, SMTP_SECURE)."
    );
  }

  const host = process.env.SMTP_HOST;
  const port = Number(process.env.SMTP_PORT);

  // true for 465, false for 587
  const secure =
    String(process.env.SMTP_SECURE || "").toLowerCase() === "true" || port === 465;

  const transporter = nodemailer.createTransport({
    host,
    port,
    secure,
    auth: {
      user: process.env.SMTP_USER,
      pass: process.env.SMTP_PASS,
    },
    // Gmail on 587 usually needs TLS
    requireTLS: !secure,
  });

  // Prove SMTP is reachable + login works (throws if not)
  await transporter.verify();

  const from = process.env.SMTP_FROM || process.env.SMTP_USER;
  const to = process.env.FAIL_EMAIL_TO;

  const info = await transporter.sendMail({
    from,
    to,
    subject,
    text: text || "",
    html: html || undefined,
    attachments,
  });

  // If SMTP rejected, throw so caller logs REAL issue
  if (info.rejected && info.rejected.length > 0) {
    throw new Error(
      `SMTP rejected recipients: ${info.rejected.join(", ")} | response=${info.response || "N/A"}`
    );
  }

  return info;
}