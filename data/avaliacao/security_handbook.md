# Security Handbook — Acme Tech

## Passwords and authentication

Every employee must use a password with at least 14 characters, mixing letters, numbers and symbols. Passwords expire every 90 days, and the last 12 passwords cannot be reused. We strongly recommend the company password manager, which generates and stores unique passwords for each system, so that a leak in one service does not expose the others.

Multi-factor authentication is mandatory for email, the VPN, the code repository and the cloud console. Authentication codes are never shared with anyone, including the IT helpdesk. If someone asks you for a code by phone or chat, treat it as a phishing attempt and report it.

## Reporting incidents

Suspicious emails, lost devices and any unusual access must be reported to the security team within 1 hour of being noticed. Send the report to security@acmetech.example or use the Report Phishing button in the email client, which also removes the message from your inbox. Do not delete the message before reporting it, and do not click links or open attachments to see what happens.

Reporting quickly matters more than being certain. The security team prefers a hundred false alarms to one missed incident, and no one is penalized for reporting in good faith.

## Incident severity levels

The security team classifies each incident and responds according to the level below.

| Level | Description | First response |
|---|---|---|
| SEV-1 | Confirmed data leak or production system compromised | 15 minutes |
| SEV-2 | Suspected compromise of an employee account | 1 hour |
| SEV-3 | Policy violation or low-risk phishing report | next business day |

During a SEV-1 incident, the security lead can order the shutdown of any system without prior approval. A written report is delivered to the board within 5 business days after the incident is closed.

## Devices and data protection

All laptops and phones that access company data must have full-disk encryption enabled, and the setting is verified automatically every day. Devices that fail the check lose access to internal systems until the problem is fixed. Lost or stolen devices must be reported immediately, so that they can be locked and wiped remotely.

Removable USB drives are blocked by default on company laptops. An exception can be requested through a helpdesk ticket and is valid for 30 days. Confidential documents must be stored only in the corporate cloud folders and never sent to personal email accounts or personal messaging apps.

## Security training

Every new employee must complete the security awareness training within 30 days of joining. The course takes about 2 hours and ends with a quiz that requires a score of at least 80% to pass. After that, everyone repeats a shorter refresher course every year. Phishing simulations are sent at random to all employees throughout the year, and the results are used only to improve the training, never to punish individuals.
