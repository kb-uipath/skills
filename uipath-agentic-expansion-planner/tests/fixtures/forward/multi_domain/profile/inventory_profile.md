# Inventory profile

Profile schema: `1.1`
Source file: `inventory.csv`
Source name: `inventory.csv`
Source SHA-256: `c951f3f322663c2b6dcef2a58b94b69a5744b8cd55a031163b10c5e2a89ce24f`
Generated UTC: `2026-07-21T21:57:33Z`
Sheets: 1
Rows: 12
Columns: 11
Latest source record date: 2026-07-02

## Sheets
| sheet | rows | columns |
| --- | --- | --- |
| inventory | 12 | 11 |


## Detected core field mapping
| field | detected_column | coverage_pct |
| --- | --- | --- |
| use_case_name | Automation Name | 100.0 |
| description | Business Problem | 100.0 |
| status | Lifecycle Status | 100.0 |
| department | Department | 100.0 |
| owner | Process Owner | 66.7 |
| systems | Applications | 91.7 |
| volume | Annual Volume | 83.3 |
| weekly_volume | not detected | 0.0 |
| annual_volume | Annual Volume | 83.3 |
| handling_time | Average Handling Minutes | 91.7 |
| hours_saved | not detected | 0.0 |
| value | not detected | 0.0 |
| priority | Priority Band | 100.0 |
| date | Last Updated | 100.0 |


## Data quality flags
- Missing core fields for full-quality output: none detected
- No value or volume fields detected: False
- Duplicate name groups detected: 0

## Normalized status counts
| status_category | count |
| --- | --- |
| excluded | 4 |
| idea | 1 |
| pipeline | 3 |
| production | 4 |


## Detailed lifecycle status counts
| lifecycle_status | count |
| --- | --- |
| cancelled | 1 |
| deployed | 4 |
| duplicate | 1 |
| idea | 1 |
| paused | 1 |
| pipeline | 3 |
| retired | 1 |


## Top departments
| department | count |
| --- | --- |
| Finance | 2 |
| IT/CIO Assurance | 2 |
| Human Resources | 2 |
| Finance Assurance | 1 |
| Procurement | 1 |
| Procurement Risk | 1 |
| Procurement Operations | 1 |
| IT Operations | 1 |
| People Operations | 1 |


## Numeric fields
| column | count | median | max | sum |
| --- | --- | --- | --- | --- |
| Annual Volume | 10 | 3200.0 | 26400.0 | 74350.0 |
| Average Handling Minutes | 11 | 12.0 | 35.0 | 147.0 |
| Last Updated | 12 | 2026.0 | 2026.0 | 24310.0 |


## Frequent terms from names and descriptions
| term | count |
| --- | --- |
| evidence | 6 |
| access | 5 |
| intake | 4 |
| onboarding | 4 |
| supplier | 3 |
| invoices | 3 |
| checks | 3 |
| fields | 3 |
| vendor | 3 |
| privileged | 3 |
| invoice | 2 |
| mailbox | 2 |
| required | 2 |
| submissions | 2 |
| queue | 2 |
| match | 2 |
| exception | 2 |
| worklist | 2 |
| reviewer | 2 |
| posting | 2 |
| tax | 2 |
| before | 2 |
| submitted | 2 |
| routes | 2 |
| exceptions | 2 |


## Representative rows
| inventory_id | sheet | row_number | Automation Name | Business Problem | Lifecycle Status | Department | Process Owner | Applications |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| INV-INVENTORY-R00002 | inventory | 2 | Supplier invoice mailbox intake | Reads shared-mailbox invoices, checks required fields, and places complete submissions in the ERP intake queue. | Live - unattended | Finance | Finance Operations Lead | Shared Mailbox;ERP Finance;Document Repository |
| INV-INVENTORY-R00003 | inventory | 3 | PO match exception worklist | Builds a reviewer queue for invoices that fail two- or three-way match and attaches purchase order context. | Pilot / UAT | Finance |  | ERP Finance;Procurement Portal |
| INV-INVENTORY-R00004 | inventory | 4 | Invoice posting confirmation archive | Stores posting confirmations and payment-run evidence for resolved invoices. | Retired after ERP patch | Finance Assurance | Finance Controls Manager | ERP Finance;Document Repository |
| INV-INVENTORY-R00005 | inventory | 5 | Vendor onboarding request intake | Captures supplier requests and checks tax, banking, and contact fields before procurement review. | Production | Procurement | Supplier Enablement Lead | Supplier Portal;Procurement Queue |
| INV-INVENTORY-R00006 | inventory | 6 | Vendor risk evidence review | Compares submitted insurance, tax, and policy documents against onboarding requirements and routes exceptions. | Approved backlog | Procurement Risk | Supplier Risk Lead | Supplier Portal;Document Repository;Policy Library |
| INV-INVENTORY-R00007 | inventory | 7 | Vendor master record creation | Creates approved supplier master records after onboarding review. | Paused - ERP migration | Procurement Operations |  | ERP Vendor Master |
| INV-INVENTORY-R00008 | inventory | 8 | Quarterly access evidence pull | Extracts account and entitlement evidence for quarterly privileged-access certification. | Deployed | IT/CIO Assurance | Access Governance Manager | Identity Governance;Directory;Evidence Repository |
| INV-INVENTORY-R00009 | inventory | 9 | Privileged access exception narrative | Prepares a reviewer worklist and evidence bundle for privileged-access exceptions. | UAT | IT/CIO Assurance | Security Assurance Lead | Identity Governance;Ticketing;Policy Library |
| INV-INVENTORY-R00010 | inventory | 10 | Access evidence pull - legacy | Legacy duplicate extract retained during dashboard migration; details are no longer maintained. | Duplicate of quarterly access evidence pull | IT Operations |  | Directory;Legacy BI |
| INV-INVENTORY-R00011 | inventory | 11 | New-hire packet completeness check | Checks submitted onboarding forms for required fields before HR operations review. | Operational | Human Resources | HR Onboarding Manager | HR Case Portal;Document Repository |


## Inventory IDs
| inventory_id | name | status | sheet | row_number |
| --- | --- | --- | --- | --- |
| INV-INVENTORY-R00002 | Supplier invoice mailbox intake | production | inventory | 2 |
| INV-INVENTORY-R00003 | PO match exception worklist | pipeline | inventory | 3 |
| INV-INVENTORY-R00004 | Invoice posting confirmation archive | excluded | inventory | 4 |
| INV-INVENTORY-R00005 | Vendor onboarding request intake | production | inventory | 5 |
| INV-INVENTORY-R00006 | Vendor risk evidence review | pipeline | inventory | 6 |
| INV-INVENTORY-R00007 | Vendor master record creation | excluded | inventory | 7 |
| INV-INVENTORY-R00008 | Quarterly access evidence pull | production | inventory | 8 |
| INV-INVENTORY-R00009 | Privileged access exception narrative | pipeline | inventory | 9 |
| INV-INVENTORY-R00010 | Access evidence pull - legacy | excluded | inventory | 10 |
| INV-INVENTORY-R00011 | New-hire packet completeness check | production | inventory | 11 |
| INV-INVENTORY-R00012 | Benefits life-event intake | idea | inventory | 12 |
| INV-INVENTORY-R00013 | Termination checklist tracker | excluded | inventory | 13 |
