# Audience policy (exercise version)

1. **Marketing messages** (email, push, SMS) require the customer's **latest** consent
   record for that channel to be `granted`. No record means no consent.
2. Customers with an **open complaint** are excluded from all marketing audiences.
3. Customers with `email_status = 'bounced'` are excluded from email audiences.
4. **Service / transactional messages** about an active booking do not need marketing
   consent, but they must be officially classified as service messages by Legal. A CRM
   manager cannot decide this alone. Service messages are not built as marketing audiences.
5. One person should receive one message. Duplicate customer records must not result
   in duplicate sends.
6. Audiences are always counted as distinct people.
