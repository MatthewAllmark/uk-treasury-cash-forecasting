# Bank of England data cache

- Downloaded: 2026-10-29T20:19:57+00:00
- File: `boe_iadb.csv` (unmodified response body)
- SHA-256: `be854625335af1ec641fbabae9435d8a187379de13e8d939fac77f2b9076a5d5`
- Data rows: 4250
- First DATE cell: 04 Jan 2010
- Last DATE cell: 28 Oct 2026

## Source

Bank of England Interactive Statistical Database (IADB), CSV endpoint:

https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Jan/2010&Dateto=now&SeriesCodes=IUDBEDR,IUDSOIA,IUDSNPY,IUDMNPY,IUDLNPY,XUDLUSS,XUDLERS&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N

Database home: https://www.bankofengland.co.uk/boeapps/database/

`CSVF=TN` asks for series codes in the header. `UsingCodes=Y` selects by code.
`VPD=Y` includes provisional observations, which the Bank may revise.
`Dateto=now` requests the latest published day at the time of the download.

The file is cached exactly as returned. Blank cells (a series not yet published
on the newest business day) are left blank. This project does not interpolate them.

## Retrieval

- OK: `treasury-analytics-portfolio/1.0 (educational; +https://github.com/MatthewAllmark)`

## Series

| Code | Description | Unit |
| --- | --- | --- |
| `IUDBEDR` | Official Bank Rate | percent per annum |
| `IUDSOIA` | SONIA (Sterling Overnight Index Average) | percent per annum |
| `IUDSNPY` | Yield from British Government Securities, 5 year Nominal Par Yield | percent per annum |
| `IUDMNPY` | Yield from British Government Securities, 10 year Nominal Par Yield | percent per annum |
| `IUDLNPY` | Yield from British Government Securities, 20 year Nominal Par Yield | percent per annum |
| `XUDLUSS` | Spot exchange rate, US dollar into sterling | USD per GBP |
| `XUDLERS` | Spot exchange rate, euro into sterling | EUR per GBP |

## Licence

Contains public sector information licensed under the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

Also subject to the Bank of England terms and conditions (https://www.bankofengland.co.uk/legal/terms-and-conditions).

This is an independent educational portfolio. It is not affiliated with, endorsed
by, or published by the Bank of England.
