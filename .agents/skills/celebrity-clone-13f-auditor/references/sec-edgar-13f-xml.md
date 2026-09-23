# SEC EDGAR 13F XML Parsing

## How to fetch the raw 13F XML

### Step 1: Get accession number

```python
url = f"https://data.sec.gov/submissions/CIK{0001709323}.json"
# response → filings.recent.form[] → find "13F-HR"
# → filings.recent.accessionNumber[i] → e.g. "0002043585-26-000013"
```

### Step 2: Find XML files in the accession

```python
acc = "0002043585-26-000013"
base = f"https://www.sec.gov/Archives/edgar/data/1709323/{acc.replace('-','')}"
index = f"{base}/{acc}-index.html"
# Parse index HTML for href="*13fhciq*.xml" or href="*infotable*.xml"
```

### Step 3: Parse the raw XML

**Namespace:** `ns1` — `http://www.sec.gov/edgar/document/thirteenf/informationtable`

**File name:** `13fhciqNNN.xml` (most filers) or `infotable.xml` (some filers)

**Structure:**
```xml
<?xml version="1.0"?>
<ns1:informationTable xmlns:ns1="http://www.sec.gov/edgar/document/thirteenf/informationtable">
  <ns1:infoTable>
    <ns1:nameOfIssuer>ALPHABET INC</ns1:nameOfIssuer>
    <ns1:titleOfClass>CAP STK CL A</ns1:titleOfClass>
    <ns1:cusip>02079K305</ns1:cusip>
    <ns1:value>731351348</ns1:value>   <!-- in $1000s -->
    <ns1:shrsOrPrnAmt>
      <ns1:sshPrnamt>2543300</ns1:sshPrnamt>
      <ns1:sshPrnamtType>SH</ns1:sshPrnamtType>
    </ns1:shrsOrPrnAmt>
    <ns1:investmentDiscretion>SOLE</ns1:investmentDiscretion>
    <ns1:votingAuthority>
      <ns1:Sole>2543300</ns1:Sole>
      <ns1:Shared>0</ns1:Shared>
      <ns1:None>0</ns1:None>
    </ns1:votingAuthority>
  </ns1:infoTable>
  ...
</ns1:informationTable>
```

**Key fields:**
| XML Path | Meaning |
|---|---|
| `ns1:nameOfIssuer` | Company name (may contain minor typos) |
| `ns1:value` | Position value in **thousands** of USD (×1000 for actual $) |
| `ns1:shrsOrPrnAmt/ns1:sshPrnamt` | Share count |
| `ns1:putCall` | "Put" or "Call" if options; absent for equities |
| `ns1:cusip` | CUSIP identifier |

## XML parsing approaches

### ElementTree (preferred — works when XML is well-formed)

```python
import xml.etree.ElementTree as ET
root = ET.fromstring(xml_text)
ns = {'ns1': 'http://www.sec.gov/edgar/document/thirteenf/informationtable'}
tables = root.findall('.//ns1:infoTable', ns)
for tbl in tables:
    name = tbl.find('ns1:nameOfIssuer', ns).text
    value_x1000 = int(tbl.find('ns1:value', ns).text)
    shares = int(tbl.find('ns1:shrsOrPrnAmt/ns1:sshPrnamt', ns).text)
```

### Regex fallback (when XML has HTML entities that break ET parser)

```python
tables = re.findall(r'<ns1:infoTable>(.*?)</ns1:infoTable>', xml_text, re.DOTALL)
for tbl in tables:
    name = re.search(r'<ns1:nameOfIssuer>([^<]+)', tbl).group(1)
    value = re.search(r'<ns1:value>([^<]+)', tbl).group(1)
```

## Known edge cases

| Issue | Symptom | Fix |
|---|---|---|
| **Name typo** | "PINDUDUO INC" vs "PINDUODUO INC" | Use substring matching fallback |
| **Missing `<ticker>` element** | Ticker not in SEC XML | Match by `nameOfIssuer` + `cusip` |
| **XSLT-rendered XML** | `xslForm13F_X02/13fhciq.xml` wraps data in HTML | Always prefer raw XML (no `xslForm13F_X02` in path) |
| **File naming varies** | Some filings use `infotable.xml` instead of `13fhciq*.xml` | Search for both patterns |
| **HTML entities in raw XML** | `&amp;`, `&nbsp;` break ET parser | Use regex fallback |
| **`<putCall>` absent** | Equity positions omit this field | Check existence before reading |

## CIK inventory for tracked investors

| Institution | CIK | 13F Active | Latest Filing |
|---|---|---|---|
| Himalaya Capital Management LLC | `0001709323` | ✅ | 2026-05-15 |
| Pabrai Investment Fund 2, L.P. | `0001571785` | ❌ | No 13F (D/A only) |
| PABRAI MOHNISH (individual) | `0001173334` | ❌ | Last 13F: 2012 |
| Aquamarine Capital Management, LLC | `0001404599` | ❌ | Last 13F: 2022 |
| H&H International Investment, LLC | `0001759760` | ✅ | 2026-05-19 |

> Dataroma shows Q1 2026 data for Pabrai and Aquamarine even though SEC has no recent 13F filings. The source may be non-SEC channels, or the filing CIK differs from what we found.
