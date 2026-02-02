#!/usr/bin/env python3
"""
Send news summary via email.
Reads the latest export file and sends it to the configured email address.
"""
import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def get_latest_export_files(export_dir: str = "exports") -> tuple[Path | None, Path | None]:
    """Get the latest txt and md export files."""
    export_path = Path(export_dir)
    
    if not export_path.exists():
        return None, None
    
    txt_files = sorted(export_path.glob("notebooklm_urls_*.txt"), reverse=True)
    md_files = sorted(export_path.glob("notebooklm_news_*.md"), reverse=True)
    
    txt_file = txt_files[0] if txt_files else None
    md_file = md_files[0] if md_files else None
    
    return txt_file, md_file


def read_file_content(filepath: Path | None, max_chars: int = 50000) -> str:
    """Read file content with size limit."""
    if not filepath or not filepath.exists():
        return ""
    
    content = filepath.read_text(encoding="utf-8")
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n... (truncated)"
    
    return content


def build_email_body(txt_file: Path | None, md_file: Path | None) -> tuple[str, str]:
    """Build plain text and HTML email body."""
    today = datetime.now().strftime("%Y-%m-%d")
    
    # Plain text version (URLs for easy copy)
    txt_content = read_file_content(txt_file)
    plain_body = f"""📰 每日新闻热点 - {today}

以下是今日热点新闻链接，可直接复制粘贴到 NotebookLM：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{txt_content}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

使用方法：
1. 打开 NotebookLM (https://notebooklm.google.com)
2. 创建或打开 Notebook
3. 点击 "Add Source" → "Website URL"
4. 粘贴上面的链接列表

---
由 News Summary Pipeline 自动生成
"""
    
    # HTML version (with markdown content)
    md_content = read_file_content(md_file)
    
    # Simple markdown to HTML conversion
    html_content = md_content.replace("\n", "<br>\n")
    html_content = html_content.replace("# ", "<h2>").replace("## ", "<h3>")
    
    html_body = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
               max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }}
        h1 {{ color: #2563eb; border-bottom: 2px solid #e2e8f0; padding-bottom: 10px; }}
        h2, h3 {{ color: #1e293b; margin-top: 24px; }}
        a {{ color: #2563eb; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .urls {{ background: #f8fafc; padding: 16px; border-radius: 8px; 
                 font-family: monospace; white-space: pre-wrap; word-break: break-all; }}
        .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e2e8f0; 
                   color: #64748b; font-size: 14px; }}
    </style>
</head>
<body>
    <h1>📰 每日新闻热点 - {today}</h1>
    
    <h2>NotebookLM 导入链接</h2>
    <div class="urls">{txt_content}</div>
    
    <h2>新闻详情</h2>
    <div class="content">{html_content}</div>
    
    <div class="footer">
        <p><strong>使用方法：</strong></p>
        <ol>
            <li>打开 <a href="https://notebooklm.google.com">NotebookLM</a></li>
            <li>创建或打开 Notebook</li>
            <li>点击 "Add Source" → "Website URL"</li>
            <li>复制上面的链接列表粘贴</li>
        </ol>
        <p>由 News Summary Pipeline 自动生成</p>
    </div>
</body>
</html>
"""
    
    return plain_body, html_body


def send_email(
    subject: str,
    plain_body: str,
    html_body: str,
    to_email: str,
    smtp_server: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
):
    """Send email with both plain text and HTML versions."""
    # Create message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_email
    
    # Attach both versions
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    
    # Send
    context = ssl.create_default_context()
    
    with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_user, to_email, msg.as_string())
    
    print(f"✅ Email sent to {to_email}")


def main():
    # Get config from environment variables
    smtp_server = os.environ.get("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    email_to = os.environ.get("EMAIL_TO", smtp_user)
    
    if not smtp_user or not smtp_password:
        print("❌ SMTP credentials not configured. Set SMTP_USER and SMTP_PASSWORD.")
        print("   Skipping email notification.")
        return
    
    # Get latest export files
    txt_file, md_file = get_latest_export_files()
    
    if not txt_file:
        print("❌ No export files found in exports/ directory")
        return
    
    print(f"📄 Found export: {txt_file.name}")
    
    # Build email
    today = datetime.now().strftime("%Y-%m-%d")
    subject = f"📰 每日新闻热点 - {today}"
    plain_body, html_body = build_email_body(txt_file, md_file)
    
    # Send
    send_email(
        subject=subject,
        plain_body=plain_body,
        html_body=html_body,
        to_email=email_to,
        smtp_server=smtp_server,
        smtp_port=smtp_port,
        smtp_user=smtp_user,
        smtp_password=smtp_password,
    )


if __name__ == "__main__":
    main()
