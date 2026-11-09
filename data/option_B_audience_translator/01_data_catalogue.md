# CRM data catalogue (synthetic, FICTIONAL)

Database: `crm_case.sqlite` (SQLite). Today's date for this exercise is **2026-11-06**.

> Honest disclaimer: like most real catalogues, this one is incomplete. Treat it as a
> starting point, not as the truth.

## customers
One row per customer record.
| Column | Description |
|---|---|
| customer_id | Primary key |
| email_hash | Hashed email address |
| country_residence | Country of residence as captured at signup |
| language | Preferred communication language |
| loyalty_tier | Base / Silver / Gold / Platinum |
| created_at | Date the record was created |
| merged_into | If set, this record was merged into the referenced customer_id |
| email_status | `active` or `bounced` |
| has_app | 1 if the customer has installed the app |

## consent
Consent history. Each change creates a new row.
| Column | Description |
|---|---|
| consent_id | Primary key |
| customer_id | FK customers |
| channel | `email`, `push`, `sms` |
| status | `granted` or `revoked` |
| updated_at | Timestamp of the change |
| source | Where the change was captured |

## bookings
| Column | Description |
|---|---|
| booking_id | Primary key |
| customer_id | FK customers |
| booking_channel | `app`, `web`, `counter`, `partner` |
| created_at | Date the booking was made |
| pickup_date / return_date | Rental period |
| pickup_station | Station code (LIS1 = Lisbon airport) |
| vehicle_class | Economy, Compact, SUV, Premium, Van |
| net_revenue_eur | Net revenue in EUR after discounts |
| status | `confirmed` (future), `completed`, `cancelled`, `no_show` |
| cancelled_at | Date of cancellation |

## app_events
App activity of customers with the app. Events are available from mid-2025.
| Column | Description |
|---|---|
| event_id | Primary key |
| customer_id | FK customers |
| event_type | `app_open`, `booking_started`, `booking_completed` |
| event_ts | Timestamp |

## complaints
| Column | Description |
|---|---|
| complaint_id | Primary key |
| customer_id | FK customers |
| opened_at / closed_at | Dates |
| status | `open` or `closed` |
| topic | Free category |

## Not available
There is no table with campaign or message history (who was contacted, when, through which channel).
