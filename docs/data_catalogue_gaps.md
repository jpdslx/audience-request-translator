# What the data catalogue doesn't say

Things I found in `crm_case.sqlite` that the catalogue doesn't mention, and how the tool handles each.
These are the first additions I'd propose to the catalogue.

| What I found | How big | How the tool handles it |
|---|---|---|
| Market (country of residence) is written several ways: `DE`, `DEU`, `Germany`, `de` (same for every market) | Every market | Treated as one market |
| Records merged into another customer (`merged_into` set) still carry their own bookings and consent | 70 records | Counted as the person they were merged into (same email address) |
| Duplicate records that were never merged (same `email_hash`) | 90 groups | One person per email address |
| Duplicates disagree on their latest email consent | 31 people | Most recent record across all their records wins; two records updated at the same moment that disagree count as no |
| Two spellings of cancelled: `cancelled` and `canceled` | 287 of 2,005 cancellations | Treated as one status |
| Customers with no consent record at all | 443 | No record means no consent |
| `has_app = 1` but no app activity | 125 customers | "App user" is defined from app events, not the flag |
| Language and country don't always match (e.g. Germany residents who prefer English) | 213 in Germany, 115 in Spain | Market is country of residence; preferred language is a separate filter |
| No message or contact history | n/a | Can't filter on past contact; the tool says so |

Questions for the catalogue owner:
- Which record is the source of truth when duplicates disagree (consent, loyalty tier)?
- Should `has_app` be retired, or defined (installed? logged in?)?
- Is there an agreed definition for "active", "lapsed" or "high-value" customers that the tool should reuse?
