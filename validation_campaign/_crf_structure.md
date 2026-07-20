# Custom_Run_Filter Structure Inventory (parser design)

## Folder listings
### AAPL
- `AAPL 2026 Q2 - Industrial Template v27.6.xlsx` (869,048 bytes)
- `Custom_Run_Filter_2026-05-04-(19-46)-AAPL.xlsx` (233,099 bytes)
- `manifest.json` (429 bytes)

### MSFT
- `Custom_Run_Filter_2026-05-27-(15-48)-MSFT.xlsx` (233,271 bytes)
- `manifest.json` (440 bytes)
- `MSFT 2026 Q3 - Industrial Template v27.6.xlsx` (880,581 bytes)

### AMZN
- `AMZN 2026 Q1 - Industrial Template v27.6.xlsx` (870,279 bytes)
- `Custom_Run_Filter_2026-05-04-(17-30)-AMZN.xlsx` (235,401 bytes)
- `manifest.json` (456 bytes)

### TJX
- `Custom_Run_Filter_2026-04-06-(16-43)-TJX.xlsx` (237,021 bytes)
- `manifest.json` (458 bytes)
- `TJX 2026 Q4 - Industrial Template v27.6.xlsx` (871,543 bytes)

## Sheet roles
| Company | Proprietary (~4k rows) | Summary | Summary cols | Ticker rows | Ticker cols | Trailer start |
|---|---|---|---|---|---|---|
| AAPL | `AAPL` | `Summary` | 111 | 4172 | 103 | 265 |
| MSFT | `MSFT` | `Summary` | 111 | 4180 | 103 | 265 |
| AMZN | `AMZN` | `Summary` | 111 | 4169 | 103 | 265 |
| TJX | `TJX` | `Summary` | 111 | 4195 | 103 | 265 |

## Cross-company consistency
- Summary headers identical across all 4: **True**
- Sheet pattern: `[TICKER, Summary]` for all (TICKER name differs).

### Dimension comparison
```json
{
  "AAPL": {
    "rows": 4172,
    "max_width": 103,
    "date_row": 15,
    "fq_row": 16,
    "fy_row": 146,
    "n_date_periods": 102,
    "n_fq_periods": 102,
    "n_fy_periods": 102,
    "ts_metric_count": 121,
    "post_scalar_count": 118,
    "real_label_count": 224,
    "trailer_start": 265,
    "trailer_rows": 3908,
    "meta_kv_count": 11
  },
  "MSFT": {
    "rows": 4180,
    "max_width": 103,
    "date_row": 15,
    "fq_row": 16,
    "fy_row": 146,
    "n_date_periods": 102,
    "n_fq_periods": 102,
    "n_fy_periods": 102,
    "ts_metric_count": 121,
    "post_scalar_count": 118,
    "real_label_count": 224,
    "trailer_start": 265,
    "trailer_rows": 3916,
    "meta_kv_count": 11
  },
  "AMZN": {
    "rows": 4169,
    "max_width": 103,
    "date_row": 15,
    "fq_row": 16,
    "fy_row": 146,
    "n_date_periods": 102,
    "n_fq_periods": 102,
    "n_fy_periods": 102,
    "ts_metric_count": 121,
    "post_scalar_count": 118,
    "real_label_count": 224,
    "trailer_start": 265,
    "trailer_rows": 3905,
    "meta_kv_count": 11
  },
  "TJX": {
    "rows": 4195,
    "max_width": 103,
    "date_row": 15,
    "fq_row": 16,
    "fy_row": 146,
    "n_date_periods": 102,
    "n_fq_periods": 102,
    "n_fy_periods": 102,
    "ts_metric_count": 122,
    "post_scalar_count": 117,
    "real_label_count": 224,
    "trailer_start": 265,
    "trailer_rows": 3931,
    "meta_kv_count": 11
  }
}
```

### Meta KV diffs vs AAPL
```json
{
  "AAPL": {
    "missing": [],
    "extra": []
  },
  "MSFT": {
    "missing": [],
    "extra": []
  },
  "AMZN": {
    "missing": [],
    "extra": []
  },
  "TJX": {
    "missing": [],
    "extra": []
  }
}
```

### Time-series label diffs vs AAPL
```json
{
  "AAPL": {
    "missing": [],
    "extra": []
  },
  "MSFT": {
    "missing": [],
    "extra": []
  },
  "AMZN": {
    "missing": [],
    "extra": []
  },
  "TJX": {
    "missing": [],
    "extra": [
      "Diluted Net Income"
    ]
  }
}
```

### Real (non-numeric) label diffs vs AAPL
```json
{
  "AAPL": {
    "missing": [],
    "extra": []
  },
  "MSFT": {
    "missing": [],
    "extra": []
  },
  "AMZN": {
    "missing": [],
    "extra": []
  },
  "TJX": {
    "missing": [],
    "extra": []
  }
}
```

## AAPL deep dive (ticker sheet)
- Title: {'row': 1, 'cells': [None, 'AAPL US Equity'], 'width': 2}
- date row=15 (102 periods)
  - first10: ['2000-12-30 00:00:00', '2001-03-31 00:00:00', '2001-06-30 00:00:00', '2001-09-29 00:00:00', '2001-12-29 00:00:00', '2002-03-30 00:00:00', '2002-06-29 00:00:00', '2002-09-28 00:00:00', '2002-12-28 00:00:00', '2003-03-29 00:00:00']
  - last5: ['2025-03-29 00:00:00', '2025-06-28 00:00:00', '2025-09-27 00:00:00', '2025-12-27 00:00:00', '2026-03-28 00:00:00']
- Fiscal Quarter row=16 (102 periods)
  - first10: ['2001 Q1', '2001 Q2', '2001 Q3', '2001 Q4', '2002 Q1', '2002 Q2', '2002 Q3', '2002 Q4', '2003 Q1', '2003 Q2']
  - last5: ['2025 Q2', '2025 Q3', '2025 Q4', '2026 Q1', '2026 Q2']
- Fiscal Year row=146 (102 periods)
  - first10: ['2001', '2001', '2001', '2001', '2002', '2002', '2002', '2002', '2003', '2003']
  - last5: ['2025', '2025', '2025', '2026', '2026']
- Trailer numeric block starts row 265 (3908 rows, max_width=2)

### Meta scalars (A/B)
- r2: `Company` = APPLE INC
- r3: `Ticker` = AAPL
- r4: `Fiscal Year Closing` = 09/2026
- r5: `Current Price (Live Price)` = 276.83
- r6: `Industry Sector` = Technology
- r7: `Industry Subgroup` = Computers
- r8: `Current Enterprise Value (not-diluted)` = 4004016.76148
- r9: `Current Market Capitalization` = 4065900.76148
- r10: `Expected Next Earnings Report Datetime` = 2026-07-31
- r11: `Latest Fiscal Quarter` = 03/26 Q2
- r12: `Latest Annual Earnings Date` = 2025-10-30

### Time-series metrics (121)
- r18: `Shares Outstanding Diluted Average (MM)` (n=102) first=['18881.52', '19757.472', '20099.0713'] last=['14863.609', '14810.356', '14725.873']
- r19: `Preferred Stock` (n=102) first=['3', '0', '0'] last=['0', '0', '0']
- r20: `Total Assets` (n=102) first=['5986', '6130', '6071'] last=['359241', '379297', '371082']
- r21: `Intangible Assets` (n=101) first=['0', '0', '76'] last=['0', '0', '21334']
- r22: `Total Liabilities` (n=102) first=['2274', '2392', '2213'] last=['285508', '291107', '264591']
- r23: `Net Income` (n=102) first=['-195', '43', '61'] last=['27466', '42097', '29578']
- r25: `Dividends per Share` (n=102) first=['0', '0', '0'] last=['0.26', '0.26', '0.26']
- r26: `Total Current Assets` (n=102) first=['4926', '5345', '5248'] last=['147957', '158104', '144114']
- r27: `Total Current Liabilities` (n=102) first=['1637', '1795', '1614'] last=['165631', '162367', '134641']
- r28: `Interest Expense` (n=91) first=['5', '10', '4'] last=['930', '998', '1002']
- r29: `Depreciation, Depletion and Amortization` (n=102) first=['24', '46', '26'] last=['3127', '3214', '3439']
- r30: `Total Equity` (n=102) first=['3712', '3738', '3858'] last=['73733', '88190', '106491']
- r31: `Revenue` (n=102) first=['1007', '1431', '1475'] last=['102466', '143756', '111184']
- r32: `Earnings Announcement Date` (n=102) first=['2001-01-17 00:00:00', '2001-04-18 00:00:00', '2001-07-17 00:00:00'] last=['2025-10-30 00:00:00', '2026-01-29 00:00:00', '2026-04-30 00:00:00']
- r33: `EBIT` (n=102) first=['-420', '-8', '42'] last=['32427', '50852', '35885']
- r34: `Income Taxes` (n=102) first=['-88', '19', '26'] last=['5338', '8905', '6255']
- r35: `Net Fixed Assets` (n=102) first=['325', '331', '347'] last=['61039', '50159', '50116']
- r36: `Weighted Average Cost of Capital` (n=102) first=['8.5923', '8.6733', '9.4086'] last=['10.2398', '10.8816', '12.2078']
- r37: `Enterprise Value (not-diluted)` (n=99) first=['1385.4477', '3821.159', '4247.5205'] last=['3753933.9996', '3965433.0002', '3587436.7744']
- r38: `Cash and Cash Equivalents` (n=102) first=['4065', '4144', '4218'] last=['54697', '66907', '68507']
- r39: `Short Term Debt` (n=101) first=['0', '0', '0'] last=['22446', '13824', '10307']
- r40: `Free Cash Flow` (n=102) first=['-35', '-96', '-63'] last=['26486', '51552', '26731']
- r41: `Long Term Debt` (n=99) first=['311', '317', '317'] last=['89931', '76685', '74404']
- r42: `Minority Non-Controlling Interest` (n=102) first=['0', '0', '0'] last=['0', '0', '0']
- r43: `Cost of Revenue` (n=102) first=['1028', '1046', '1041'] last=['54125', '74525', '56403']
- r50: `Capital Expenditures` (n=102) first=['-22', '-39', '-30'] last=['-3242', '-2373', '-1971']
- r51: `Retained Earnings` (n=96) first=['2090', '2133', '2317'] last=['-14264', '-2177', '12359']
- r52: `Total Operating Lease Liabilities` (n=102) first=['0', '0', '0'] last=['12490', '0', '0']
- r53: `Total Operating Lease Assets` (n=102) first=['0', '0', '0'] last=['11205', '0', '0']
- r54: `Net Income GAAP (used for RAROE calc)` (n=102) first=['-195', '43', '61'] last=['27466', '42097', '29578']
- r56: `Accumulated Depreciation` (n=102) first=['389', '390', '380'] last=['76014', '77161', '77441']
- r57: `EBITDA` (n=102) first=['-396', '38', '68'] last=['35554', '54066', '39324']
- r60: `Cash from Operations` (n=102) first=['-13', '-57', '-33'] last=['29728', '53925', '28702']
- r61: `Closing Stock Price (Q. Average)` (n=102) first=['0.3647333333333333', '0.4111709677419354', '0.3180245901639344'] last=['268.9195081967214', '262.5460317460317', '278.485']
- r62: `Month Used for CPI` (n=102) first=['200012', '20013', '20016'] last=['20259', '202512', '20263']
- r63: `CPI for fiscal month` (n=102) first=['174', '176.2', '178'] last=['324.8', '324.054', '330.213']
- r64: `Earnings per Share (diluted)` (n=102) first=['-0.01032755837453764', '0.00217639179749312', '0.003034966098159968'] last=['1.847868845312064', '2.842402978024296', '2.008573617333247']
- r65: `Market Value of Common` (n=102) first=['6886.719727999999', '8123.698882374192', '6391.998912858196'] last=['3997114.422308362', '3888400.196546031', '4100934.742405']
- r66: `Total Capitalization at Market` (n=102) first=['6889.719727999999', '8123.698882374192', '6391.998912858196'] last=['3997114.422308362', '3888400.196546031', '4100934.742405']
- r67: `Tangible Book Value per Share` (n=101) first=['0.1891942450937043', '0.1919491673229698', '0.192533085125263'] last=['4.960639101849355', '5.954617161126984', '5.782815049403183']
- r68: `Tangible Book Value per Share/Price` (n=101) first=['0.4601352233906964', '0.6035670613521564', '0.5250194084272928'] last=['0.01844655724351735', '0.0226802786601896', '0.02076526581109641']
- r69: `Net Margin` (n=102) first=['-0.1936444885799404', '0.03004891684136967', '0.04135593220338983'] last=['0.2680498897195167', '0.292836472912435', '0.2660274859692042']
- r70: `Current Assets/ Total Liabilities` (n=102) first=['2.16622691292876', '2.234531772575251', '2.371441482150926'] last=['0.5182236574807011', '0.5431130134280522', '0.5446670521673073']
- r71: `Working Capital` (n=102) first=['3289', '3550', '3634'] last=['-17674', '-4263', '9473']
- r72: `Working Capital/Debt` (n=102) first=['1.446350043975374', '1.484113712374582', '1.642114776321735'] last=['-0.06190369446740546', '-0.01464409993576245', '0.03580242714226863']
- r73: `ROE` (n=102) first=['-0.0525323275862069', '0.01150347779561263', '0.01581130119232763'] last=['0.3725062048200941', '0.4773443701099898', '0.277751171460499']
- r74: `ROA` (n=102) first=['-0.03257601069161377', '0.007014681892332789', '0.01004776807774667'] last=['0.076455638415437', '0.1109869047211025', '0.07970745010536755']
- r75: `Assets/Liabilities` (n=102) first=['2.632365875109938', '2.562709030100335', '2.743334839584275'] last=['1.258251957913614', '1.302947026351136', '1.402474007052394']
- r76: `EBIT TTM` (n=99) first=['-333', '107', '143'] last=['133050', '141070', '147366']
- r77: `Working Capital For ROC` (n=101) first=['0', '0', '0'] last=['0', '0', '0']
- r78: `ROC Greenblatt` (n=99) first=['-0.5904255319148937', '0.1867364746945899', '0.2436115843270869'] last=['2.179753927816642', '2.812456388683985', '2.940498044536675']
- r79: `ROC - WACC` (n=99) first=['-0.6999015319148937', '0.07125647469458987', '0.1512355843270869'] last=['2.077355927816642', '2.703640388683985', '2.818420044536675']
- r80: `EPS TTM` (n=99) first=['-0.001270592121213269', '0.010420522280785', '0.01017631850578326'] last=['7.464996043072252', '7.894128712864822', '8.261438625657878']
- r81: `Dividend Rate (TTM)` (n=99) first=['0', '0', '0'] last=['1.02', '1.03', '1.04']
- r82: `Gross Margin TTM` (n=99) first=['0.2302815588290136', '0.2927935787820625', '0.2937014667817084'] last=['0.4690516410716045', '0.4732528803972297', '0.4786240535882794']
- r83: `Operating Margin TTM` (n=99) first=['-0.06209211262353161', '0.01867038911184785', '0.02467644521138913'] last=['0.3197079976259188', '0.3238395195779779', '0.3264339605087697']
- r84: `Interest Coverage Ratio TTM` (n=85) first=['-15.85714285714286', '5.631578947368421', '11.91666666666667'] last=['32.28054038516815', '29.86322511974454', '29.06203915586067']
- r85: `Cash Conversion TTM` (n=99) first=['-1.84', '0.4663461538461539', '0.8439024390243902'] last=['0.8908490313364879', '1.049780517418511', '1.041093208239853']
- r86: `ROCE` (n=99) first=['0.02856668327520346', '0.03707938582162692', '0.04565772669220945'] last=['0.3103264939135567', '0.3571660202954413', '0.3778733541373605']
- r87: `PE (TTM)` (n=99) first=['-288.6182929279355', '41.19724161860422', '37.78475262943429'] last=['36.02406573896138', '33.25839257195901', '33.70902001681621']
- r88: `Dividend Yield TTM` (n=99) first=['0', '0', '0'] last=['0.003792956512674584', '0.003923121569006798', '0.003734491983410239']
- r89: `EPS Fiscal Year` (n=25) first=['-0.001270592121213269', '0.003199245596231977', '0.003385449602800715'] last=['6.134052816822412', '6.083555627206207', '7.464996043072248']
- r90: `Net Margin Fiscal Year` (n=25) first=['-0.004661570016781652', '0.01132009752699408', '0.0111164813919768'] last=['0.2530623426432028', '0.2397125576994387', '0.2691506412181824']
- r91: `Gross Margin Fiscal Year` (n=25) first=['0.2302815588290136', '0.2791710205503309', '0.2751731915579185'] last=['0.4413112957720756', '0.4620634981523393', '0.4690516410716045']
- r92: `Gross Margin Growth YOY` (n=24) first=['0.2123029823574287', '-0.01432035812503563', '-0.008409796745978082'] last=['0.01896804487130388', '0.04702395469836707', '0.0151237718348427']
- r93: `Operating Margin Fiscal Year` (n=25) first=['-0.06209211262353161', '0.008011145942180425', '0.004027710649266956'] last=['0.2982141226502472', '0.3151022287007557', '0.3197079976259188']
- r94: `Operating Margin 10 Fiscal Years` (n=16) first=['0.1196966710951994', '0.1571209513189286', '0.1916157960366947'] last=['0.2791013606157319', '0.2818892442533339', '0.2833827532985992']
- r95: `Cash Conversion Fiscal Year` (n=25) first=['-1.84', '-0.4461538461538462', '2.550724637681159'] last=['1.020918604051755', '1.139466160279935', '0.8908490313364879']
- r96: `Interest Coverage Ratio Fiscal Year` (n=25) first=['-15.85714285714286', '4.181818181818182', '3.125'] last=['29.06203915586067', 'inf', 'inf']
- r97: `Assets/Liabilities Fiscal Year` (n=25) first=['2.865778200856735', '2.858828869723105', '2.629243827160494'] last=['1.227202739224532', '1.196461335060169', '1.274773091884052']
- r98: `ROA Fiscal Year` (n=25) first=['-0.004152134196977246', '0.0103207367418228', '0.01012472487160675'] last=['0.2750983456377648', '0.2568250315085758', '0.3117962593356549']
- r99: `ROE Fiscal Year` (n=25) first=['-0.006377551020408163', '0.01587301587301587', '0.01633909542978925'] last=['1.560760145463908', '1.64593503072871', '1.519129833317511']
- r100: `Revenue Fiscal Year` (n=25) first=['5363', '5742', '6207'] last=['383285', '391035', '416161']
- r101: `Net Income Fiscal Year` (n=25) first=['-25', '65', '69'] last=['96995', '93736', '112010']
- r102: `EBIT Fiscal Year` (n=25) first=['-333', '46', '25'] last=['114301', '123216', '133050']
- r103: `Free Cash Flow Fiscal Year` (n=25) first=['-82', '-85', '125'] last=['99584', '108807', '98767']
- r104: `WACC Fiscal Year` (n=25) first=['10.9476', '9.6641', '9.2219'] last=['11.0011', '10.6262', '10.2398']
- r105: `ROC Greenblatt Fiscal Year` (n=25) first=['-0.5904255319148937', '0.07407407407407407', '0.03736920777279522'] last=['2.10204869795498', '2.203669921665415', '2.179753927816642']
- r106: `Owners Earnings to Equity (Fiscal Year)` (n=25) first=['-0.03903061224489796', '0.002197802197802198', '0.004262372720814586'] last=['1.569771183986097', '1.681018437225636', '1.505336823403361']
- r107: `Owners Earnings per Share (Fiscal Year)` (n=25) first=['-0.007776023781825205', '0.0004429724671705814', '0.0008831607659480125'] last=['6.169467730760456', '6.213227729100442', '7.397217264607786']
- r108: `Average Shares Outstanding Diluted Average (MM) Fiscal Year` (n=25) first=['19675.86575', '20317.289825', '20381.340175'] last=['15812.54725', '15408.0945', '15004.6965']
- r109: `EPS Year 10 Extrapolation` (n=13) first=['8.504614555353566', '8.188319349094947', '9.50244549399976'] last=['0.6198676034993227', '0.6656784155026022', '0.7465338443149667']
- r110: `Sum of 10 Years of Extrapolated Dividends` (n=13) first=['1.416337476241615', '2.552667003791143', '4.058380223521515'] last=['3.274958709956107', '3.339545852053834', '4.238431357845182']
- r111: `BV per Share Year 10` (n=13) first=['34.1694759531545', '29.36167739441373', '31.07686296738637'] last=['0.7212404806291233', '0.6733410695775139', '0.6812699032258057']
- r112: `RAROE (Risk Adjusted Return on Equity` (n=16) first=['0.1738067969625923', '0.2200995305021629', '0.241060018767527'] last=['0.9628812050867539', '1.030073763858885', '0.914778192731018']
- r113: `Ten Year Dividend Payout Ratio Average` (n=16) first=['0', '0', '0.006000643045072246'] last=['0.2194079356740821', '0.2074496931470158', '0.1996311293322948']
- r114: `EBITDA 3 Fiscal Year Average` (n=23) first=['31.66666666666667', '267', '819.6666666666666'] last=['125531.3333333333', '130340.6666666667', '135076.3333333333']
- r115: `EBITDA Fiscal Year` (n=25) first=['-207', '164', '138'] last=['125820', '134661', '144748']
- r116: `Total Debt Fiscal Year` (n=25) first=['317', '316', '304'] last=['123930', '119059', '112377']
- r117: `ROCE Fiscal Year` (n=25) first=['0.02856668327520346', '0.0141314703080343', '0.04240645634629494'] last=['0.3135233406034891', '0.3240013151405556', '0.3103264939135567']
- r118: `ROCE 5 Fiscal Years` (n=21) first=['0.08411819462665557', '0.1042113095845181', '0.1453596115515309'] last=['0.2820538359428957', '0.3058569230620394', '0.318106236071891']
- r119: `ROCE 10 Fiscal Years` (n=16) first=['0.1495990643939499', '0.1789918396563274', '0.2064636435524597'] last=['0.2536461745692888', '0.260290070074735', '0.2633332586522313']
- r120: `3 years Av EPS Growth (10 Years) TTM` (n=63) first=['233.3948435294624', '69.4227717007715', '79.67013192782933'] last=['1.680905365396043', '1.728376884766694', '1.741491799053041']
- r121: `3 years Av EPS Growth (10 Years) TTM Direction` (n=63) first=['P', 'P', 'P'] last=['P', 'P', 'P']
- r122: `3 years Av Revenue Growth (10 Years) TTM` (n=63) first=['7.364082717190389', '7.843427447982087', '8.506572994837404'] last=['0.6756293035013541', '0.6929654224613508', '0.6980893876899186']
- r124: `Funds from Operations 10 Year Growth Direction` (n=102) first=['N', 'N', 'N'] last=['N', 'N', 'N']
- r126: `Gross Book Value` (n=101) first=['6520', '6451', '6305'] last=['435255', '456458', '427189']
- r127: `Debt to Gross Book Value Ratio` (n=98) first=['0.04861963190184049', '0.04913966826848551', '0.05027755749405234'] last=['0.2581865802805252', '0.1982854939556323', '0.1982986453302871']
- r128: `Total Debt to EBITDA 3 Year Ratio` (n=23) first=['9.6', '0', '0'] last=['0.9872435567215623', '0.9134447678135756', '0.8319518099642423']
- r129: `Book Value Per Share` (n=102) first=['0.1964354564674878', '0.1891942450937043', '0.1919491673229698'] last=['4.960639101849355', '5.954617161126984', '7.231557680824763']
- r132: `E10` (n=63) first=['0.1437382197549622', '0.1685049732307818', '0.194371104711412'] last=['5.180752649962978', '5.340673605427186', '5.577242073364912']
- r133: `PE10` (n=63) first=['79.32339216417458', '73.0779252983162', '62.84275006943049'] last=['51.90742086454236', '49.15972237644943', '49.93238527873005']
- r134: `Min PE10` (n=24) first=['22.26334466859778', '22.26334466859778', '22.26334466859778'] last=['22.26334466859778', '22.26334466859778', '24.51118881339827']
- r135: `Max PE10` (n=24) first=['79.32339216417458', '73.0779252983162', '65.93347671847042'] last=['57.55895181649397', '57.55895181649397', '57.55895181649397']
- r136: `Min 7PE10` (n=36) first=['22.26334466859778', '22.26334466859778', '22.26334466859778'] last=['25.69251525246548', '26.1757380889526', '28.30643622388359']
- r137: `Max 7PE10` (n=36) first=['79.32339216417458', '73.0779252983162', '65.93347671847042'] last=['57.55895181649397', '57.55895181649397', '57.55895181649397']
- r138: `PE10 20th Percentile (Interpolation)` (n=24) first=['28.23175930391965', '28.23175930391965', '28.23175930391965'] last=['28.23175930391965', '28.45283580042772', '28.49011648214508']
- r139: `7PE10 20th Percentile (Interpolation)` (n=36) first=['28.70593506370093', '28.70593506370093', '28.48977608835441'] last=['39.77445913035069', '40.4049650077887', '41.60135013589199']
- r140: `PE10 Quantile Satisfied (Interpolation)` (n=102) first=['No', 'No', 'No'] last=['No', 'No', 'No']
- r141: `7PE10 Quantile Satisfied (Interpolation)` (n=102) first=['No', 'No', 'No'] last=['No', 'No', 'No']
- r142: `PE10 45th Percentile (Interpolation)` (n=24) first=['32.05326437959868', '32.05326437959868', '32.05326437959868'] last=['39.77471435218767', '40.64102187907248', '41.69590925200506']
- r143: `7PE10 45th Percentile (Interpolation)` (n=36) first=['34.11223765215399', '32.87586891672701', '31.51199939529558'] last=['45.34981350968873', '46.27401094788005', '46.53378544123854']
- r144: `Lowest of 45th Percentile PE10 or 7PE10` (n=36) first=['34.11223765215399', '32.87586891672701', '31.51199939529558'] last=['39.77471435218767', '40.64102187907248', '41.69590925200506']
- r145: `Lowest of 20th Percentile PE10 or 7PE10` (n=36) first=['28.70593506370093', '28.70593506370093', '28.48977608835441'] last=['28.23175930391965', '28.45283580042772', '28.49011648214508']
- r147: `Number of years with dividends in past 10 years` (n=66) first=['0', '0', '0'] last=['10', '10', '10']
- r148: `Dividend Policy Satisfied` (n=102) first=['No', 'No', 'No'] last=['Yes', 'Yes', 'Yes']
- r149: `Fiscal Quarter for Earnings` (n=63) first=['2010 Q4', '2011 Q1', '2011 Q2'] last=['2025 Q4', '2026 Q1', '2026 Q2']
- r150: `Min PE10 from Daily PE10s` (n=24) first=['20.73512200498604', '20.73512200498604', '20.73512200498604'] last=['20.73512200498604', '20.73512200498604', '20.73512200498604']
- r151: `Max PE10 from Daily PE10s` (n=24) first=['86.58587828078579', '76.96449399293394', '76.33665746706137'] last=['63.31049898848808', '63.31049898848808', '63.31049898848808']
- r152: `Min 7PE10 from Daily PE10s` (n=36) first=['20.88794679909775', '20.88794679909775', '20.88794679909775'] last=['22.95059115765329', '23.10464211531424', '24.97254686871825']
- r153: `Max 7PE10 from Daily PE10s` (n=36) first=['86.58587828078579', '76.96449399293394', '76.33665746706137'] last=['63.31049898848808', '63.31049898848808', '63.31049898848808']

### Post/narrow scalars (118)
- r24: `Diluted Net Income` = None
- r44: `Non-Performing Assets` = None
- r45: `Tier 1 Common Equity Ratio` = None
- r46: `Tier 1 Capital Ratio` = None
- r47: `Basel III Total Capital Ratio Fully Loaded` = None
- r48: `Efficiency Ratio` = None
- r49: `Net Interest Margin TTM` = None
- r55: `Funds from Operations` = None
- r58: `Rental Income` = None
- r59: `Property Operating Expense - As Reported` = None
- r123: `Funds from Operations 10 Year Growth` = None
- r125: `Funds from Operations per Share` = None
- r130: `Non-Performing Assets Growth QOQ` = None
- r131: `Non-Performing Assets to Total Assets` = None
- r158: `Current E10` = 5.577242073364912
- r159: `Current PE10` = 49.63564363147329
- r160: `Latest Quarter Assets/ Liabilities` = 1.402474007052394
- r161: `Dividends Since` = 2012-08-16 00:00:00
- r162: `Current Max PE10 to Enter (Lowest PE10 or 7PE10)` = 28.37382487175449
- r163: `Max Current Price to Buy` = 158.2476898570369
- r164: `1st Exit Price` = 225.6932267252422
- r165: `2nd Exit Price` = 244.3801987924168
- r166: `Expected Return @ Current Price` = -0.1847226574965062
- r167: `% Shares to sell to recoup FV @ 1st Exit price` = 1.226576464064699
- r168: `High Price in 10 years` = 286.19
- r169: `Low Price in 10 years` = 22.585
- r170: `Price change in 10 years` = 11.67168474651317
- r171: `High Price in 52 weeks` = 286.19
- r172: `Low Price in 52 weeks` = 195.27
- r173: `Price change in 52 weeks` = 0.465611717109643
- r174: `SNOA (Scaled Net Operating Assets)` = 0.330641205986817
- r175: `ROA10` = 0.2153282528169929
- r176: `ROC10` = 1.975737794966297
- r177: `CFOA` = 2.313504831816148
- r178: `Number of Consecutive Positive Growth Margins` = 25
- r179: `Profit Margin Growth` = 0.0204984257214369
- r180: `Profit Margin Stability` = 11.80488078337277
- r181: `FS_ROA` = 1
- r182: `FS_FCFTA` = 1
- r183: `FS_ACCRUAL` = 1
- r184: `FS_LEVER` = 1
- r185: `FS_LIQUID` = 1
- r186: `FS_NEQISS` = 1
- r187: `FS_DELTA_ROA` = 1
- r188: `FS_DELTA_FCFTA` = 1
- r189: `FS_DELTA_MARGIN` = 1
- r190: `FS_DELTA_TURN` = 1
- r191: `P_FS` = 1
- r192: `Current 3 year EPS 10 years Av Growth` = 1.741491799053041
- r193: `Current 3 year EPS 10 years Av Growth Direction` = P
- r194: `Current 3 year Revenue 10 years Av Growth` = 0.6980893876899186
- r195: `Current TBV/Price` = 0.02088940884081632
- r196: `Dividend Policy Satisfied` = Yes
- r197: `Expected Return Price Plus Dividends - Given Current Price` = -0.2124157702387417
- r198: `Expected Return Price Plus Dividends - Given Max Entry Price` = -0.1671158664960853
- r199: `ROCE` = 0.3778733541373605
- r200: `ROCE Fiscal Year` = 0.3103264939135567
- r201: `ROCE 5 Fiscal Years` = 0.318106236071891
- r202: `ROCE 10 Fiscal Years` = 0.2633332586522313
- r203: `Approximate Residual Earnings Value` = 67.40230496741884
- r204: `Extrapolated Price Plus Dividends` = 25.42045191727559
- r205: `EPS Latest Fiscal Year` = 7.464996043072248
- r206: `EPS Current Yield` = 0.02696599372565202
- r207: `EPS Growth Last Decade` = 0.124735977490416
- r208: `EPS Growth Direction Last Decade` = P
- r209: `Retained Earnings Average` = -0.1636181959084042
- r210: `Book Value per Share Growth per Year` = -0.1792924070372372
- r211: `ROE Average` = 1.095797481703121
- r212: `Current Dividend Yield (TTM)` = 0.003756818263916485
- r213: `Current Dividend Yield` = 0.003901311274067117
- r214: `Current PE10 (PFFO10 for REITS) Percentile` = 0.7492063492063492
- r215: `Current Enterprise Value (not-diluted)` = 4004016.76148
- r216: `Current Market Capitalization` = 4065900.76148
- r217: `EBIT TTM` = 147366
- r218: `EBIT 5 year average` = 124930.6
- r219: `EBIT TTM/EV` = 0.03680454123412043
- r220: `EBIT 5 year average/EV` = 0.03120131793699636
- r221: `Debt/Total Assets` = 0.2282810807314825
- r222: `ROC Greenblatt` = 2.940498044536675
- r223: `WACC` = 0.122078
- r224: `ROC - WACC` = 2.818420044536675
- r225: `Current Status without PE10 Percentile` = Out
- r226: `Current Status with PE10 Percentile` = Out
- r227: `Current FFO10` = None
- r228: `Current PFFO10` = None
- r229: `Current Book Value Per Share` = 7.231557680824763
- r230: `Price/Book Value Per Share` = None
- r231: `Non-Performing Assets` = None
- r232: `Tier 1 Common Equity Ratio` = None
- r233: `Tier 1 Capital Ratio` = None
- r234: `Basel III Total Capital Ratio Fully Loaded` = None
- r235: `Efficiency Ratio` = None
- r236: `Net Interest Margin TTM` = None
- r237: `Non-Performing Assets Growth QOQ` = None
- r238: `Non-Performing Assets to Total Assets` = None
- r239: `ROE` = 0.277751171460499
- r240: `Total Assets` = 371082
- r241: `Latest Owners Earnings to Equity (Fiscal Year)` = 1.505336823403361
- r242: `Latest Owners Earnings per Share (Fiscal Year)` = 7.397217264607786
- r243: `Six Month Price Change` = 0.02476493669948909
- r244: `Current Funds from Operations 10 Year Growth Direction` = N
- r245: `Current Debt to Gross Book Value Ratio` = 0.1982986453302871
- r246: `Current Gross Book Value` = 427189
- r247: `Current Total Debt to (EBITDA 3 Year Average)` = 0.8319518099642423
- r248: `Fair Stock Price (REITS)` = None
- r249: `NOI (Net Operating Income) reported for Q (REITS)` = None
- r250: `Gross Margin TTM` = 0.4786240535882794
- r251: `Gross Margin Fiscal Year` = 0.4690516410716045
- r252: `Operating Margin TTM` = 0.3264339605087697
- r253: `Operating Margin Fiscal Year` = 0.3197079976259188
- r254: `Operating Margin 10 Fiscal Years` = 0.2833827532985992
- r255: `Cash Conversion TTM` = 1.041093208239853
- r256: `Cash Conversion Fiscal Year` = 0.8908490313364879
- r257: `Interest Coverage Ratio TTM` = None
- r258: `Interest Coverage Ratio Fiscal Year` = inf
- r259: `Current Graham Instrinsic Value` = 291.5370204928446
- r260: `Graham Instrinsic Value in 7 Years` = 454.3694346271823
- r261: `Graham Expected Annualized Return` = 0.07335227081235085

### All real col-A labels (excluding numeric trailer indices)
- Company
- Ticker
- Fiscal Year Closing
- Current Price (Live Price)
- Industry Sector
- Industry Subgroup
- Current Enterprise Value (not-diluted)
- Current Market Capitalization
- Expected Next Earnings Report Datetime
- Latest Fiscal Quarter
- Latest Annual Earnings Date
- date
- Fiscal Quarter
- Shares Outstanding Diluted Average (MM)
- Preferred Stock
- Total Assets
- Intangible Assets
- Total Liabilities
- Net Income
- Diluted Net Income
- Dividends per Share
- Total Current Assets
- Total Current Liabilities
- Interest Expense
- Depreciation, Depletion and Amortization
- Total Equity
- Revenue
- Earnings Announcement Date
- EBIT
- Income Taxes
- Net Fixed Assets
- Weighted Average Cost of Capital
- Enterprise Value (not-diluted)
- Cash and Cash Equivalents
- Short Term Debt
- Free Cash Flow
- Long Term Debt
- Minority Non-Controlling Interest
- Cost of Revenue
- Non-Performing Assets
- Tier 1 Common Equity Ratio
- Tier 1 Capital Ratio
- Basel III Total Capital Ratio Fully Loaded
- Efficiency Ratio
- Net Interest Margin TTM
- Capital Expenditures
- Retained Earnings
- Total Operating Lease Liabilities
- Total Operating Lease Assets
- Net Income GAAP (used for RAROE calc)
- Funds from Operations
- Accumulated Depreciation
- EBITDA
- Rental Income
- Property Operating Expense - As Reported
- Cash from Operations
- Closing Stock Price (Q. Average)
- Month Used for CPI
- CPI for fiscal month
- Earnings per Share (diluted)
- Market Value of Common
- Total Capitalization at Market
- Tangible Book Value per Share
- Tangible Book Value per Share/Price
- Net Margin
- Current Assets/ Total Liabilities
- Working Capital
- Working Capital/Debt
- ROE
- ROA
- Assets/Liabilities
- EBIT TTM
- Working Capital For ROC
- ROC Greenblatt
- ROC - WACC
- EPS TTM
- Dividend Rate (TTM)
- Gross Margin TTM
- Operating Margin TTM
- Interest Coverage Ratio TTM
- Cash Conversion TTM
- ROCE
- PE (TTM)
- Dividend Yield TTM
- EPS Fiscal Year
- Net Margin Fiscal Year
- Gross Margin Fiscal Year
- Gross Margin Growth YOY
- Operating Margin Fiscal Year
- Operating Margin 10 Fiscal Years
- Cash Conversion Fiscal Year
- Interest Coverage Ratio Fiscal Year
- Assets/Liabilities Fiscal Year
- ROA Fiscal Year
- ROE Fiscal Year
- Revenue Fiscal Year
- Net Income Fiscal Year
- EBIT Fiscal Year
- Free Cash Flow Fiscal Year
- WACC Fiscal Year
- ROC Greenblatt Fiscal Year
- Owners Earnings to Equity (Fiscal Year)
- Owners Earnings per Share (Fiscal Year)
- Average Shares Outstanding Diluted Average (MM) Fiscal Year
- EPS Year 10 Extrapolation
- Sum of 10 Years of Extrapolated Dividends
- BV per Share Year 10
- RAROE (Risk Adjusted Return on Equity
- Ten Year Dividend Payout Ratio Average
- EBITDA 3 Fiscal Year Average
- EBITDA Fiscal Year
- Total Debt Fiscal Year
- ROCE Fiscal Year
- ROCE 5 Fiscal Years
- ROCE 10 Fiscal Years
- 3 years Av EPS Growth (10 Years) TTM
- 3 years Av EPS Growth (10 Years) TTM Direction
- 3 years Av Revenue Growth (10 Years) TTM
- Funds from Operations 10 Year Growth
- Funds from Operations 10 Year Growth Direction
- Funds from Operations per Share
- Gross Book Value
- Debt to Gross Book Value Ratio
- Total Debt to EBITDA 3 Year Ratio
- Book Value Per Share
- Non-Performing Assets Growth QOQ
- Non-Performing Assets to Total Assets
- E10
- PE10
- Min PE10
- Max PE10
- Min 7PE10
- Max 7PE10
- PE10 20th Percentile (Interpolation)
- 7PE10 20th Percentile (Interpolation)
- PE10 Quantile Satisfied (Interpolation)
- 7PE10 Quantile Satisfied (Interpolation)
- PE10 45th Percentile (Interpolation)
- 7PE10 45th Percentile (Interpolation)
- Lowest of 45th Percentile PE10 or 7PE10
- Lowest of 20th Percentile PE10 or 7PE10
- Fiscal Year
- Number of years with dividends in past 10 years
- Dividend Policy Satisfied
- Fiscal Quarter for Earnings
- Min PE10 from Daily PE10s
- Max PE10 from Daily PE10s
- Min 7PE10 from Daily PE10s
- Max 7PE10 from Daily PE10s
- Current E10
- Current PE10
- Latest Quarter Assets/ Liabilities
- Dividends Since
- Current Max PE10 to Enter (Lowest PE10 or 7PE10)
- Max Current Price to Buy
- 1st Exit Price
- 2nd Exit Price
- Expected Return @ Current Price
- % Shares to sell to recoup FV @ 1st Exit price
- High Price in 10 years
- Low Price in 10 years
- Price change in 10 years
- High Price in 52 weeks
- Low Price in 52 weeks
- Price change in 52 weeks
- SNOA (Scaled Net Operating Assets)
- ROA10
- ROC10
- CFOA
- Number of Consecutive Positive Growth Margins
- Profit Margin Growth
- Profit Margin Stability
- FS_ROA
- FS_FCFTA
- FS_ACCRUAL
- FS_LEVER
- FS_LIQUID
- FS_NEQISS
- FS_DELTA_ROA
- FS_DELTA_FCFTA
- FS_DELTA_MARGIN
- FS_DELTA_TURN
- P_FS
- Current 3 year EPS 10 years Av Growth
- Current 3 year EPS 10 years Av Growth Direction
- Current 3 year Revenue 10 years Av Growth
- Current TBV/Price
- Expected Return Price Plus Dividends - Given Current Price
- Expected Return Price Plus Dividends - Given Max Entry Price
- Approximate Residual Earnings Value
- Extrapolated Price Plus Dividends
- EPS Latest Fiscal Year
- EPS Current Yield
- EPS Growth Last Decade
- EPS Growth Direction Last Decade
- Retained Earnings Average
- Book Value per Share Growth per Year
- ROE Average
- Current Dividend Yield (TTM)
- Current Dividend Yield
- Current PE10 (PFFO10 for REITS) Percentile
- EBIT 5 year average
- EBIT TTM/EV
- EBIT 5 year average/EV
- Debt/Total Assets
- WACC
- Current Status without PE10 Percentile
- Current Status with PE10 Percentile
- Current FFO10
- Current PFFO10
- Current Book Value Per Share
- Price/Book Value Per Share
- Latest Owners Earnings to Equity (Fiscal Year)
- Latest Owners Earnings per Share (Fiscal Year)
- Six Month Price Change
- Current Funds from Operations 10 Year Growth Direction
- Current Debt to Gross Book Value Ratio
- Current Gross Book Value
- Current Total Debt to (EBITDA 3 Year Average)
- Fair Stock Price (REITS)
- NOI (Net Operating Income) reported for Q (REITS)
- Current Graham Instrinsic Value
- Graham Instrinsic Value in 7 Years
- Graham Expected Annualized Return

### First 15 rows preview (≤30 cols)
- r1: [None, 'AAPL US Equity']
- r2: ['Company', 'APPLE INC']
- r3: ['Ticker', 'AAPL']
- r4: ['Fiscal Year Closing', '09/2026']
- r5: ['Current Price (Live Price)', '276.83']
- r6: ['Industry Sector', 'Technology']
- r7: ['Industry Subgroup', 'Computers']
- r8: ['Current Enterprise Value (not-diluted)', '4004016.76148']
- r9: ['Current Market Capitalization', '4065900.76148']
- r10: ['Expected Next Earnings Report Datetime', '2026-07-31']
- r11: ['Latest Fiscal Quarter', '03/26 Q2']
- r12: ['Latest Annual Earnings Date', '2025-10-30']
- r13: []
- r14: []
- r15: ['date', '2000-12-30 00:00:00', '2001-03-31 00:00:00', '2001-06-30 00:00:00', '2001-09-29 00:00:00', '2001-12-29 00:00:00', '2002-03-30 00:00:00', '2002-06-29 00:00:00', '2002-09-28 00:00:00', '2002-12-28 00:00:00', '2003-03-29 00:00:00', '2003-06-28 00:00:00', '2003-09-27 00:00:00', '2003-12-27 00:00:00', '2004-03-27 00:00:00', '2004-06-26 00:00:00', '2004-09-25 00:00:00', '2004-12-25 00:00:00', '2005-03-26 00:00:00', '2005-06-25 00:00:00', '2005-09-24 00:00:00', '2005-12-31 00:00:00', '2006-04-01 00:00:00', '2006-07-01 00:00:00', '2006-09-30 00:00:00', '2006-12-30 00:00:00', '2007-03-31 00:00:00', '2007-06-30 00:00:00', '2007-09-29 00:00:00', '2007-12-29 00:00:00']

## Summary sheet — full field catalog (identical across AAPL/MSFT/AMZN/TJX)
- Rows: 2 (header + 1 company). Columns: 111

| # | Field | AAPL value | Kind |
|---|---|---|---|
| 1 | Company | APPLE INC | scalar |
| 2 | Ticker | AAPL | scalar |
| 3 | Current Price (Live Price) | 276.83 | scalar |
| 4 | Industry Sector | Technology | scalar |
| 5 | Industry Subgroup | Computers | scalar |
| 6 | Current Status without PE10 Percentile | Out | scalar |
| 7 | Current Status with PE10 Percentile | Out | scalar |
| 8 | Current PE10 (PFFO10 for REITS) Percentile | 0.7492063492063492 | scalar |
| 9 | Expected Next Earnings Report Datetime | 2026-07-31 | scalar |
| 10 | Latest Fiscal Quarter | 03/26 Q2 | scalar |
| 11 | Latest Annual Earnings Date | 2025-10-30 | scalar |
| 12 | Max Current Price to Buy | 158.2476898570369 | scalar |
| 13 | 1st Exit Price | 225.6932267252422 | scalar |
| 14 | 2nd Exit Price | 244.3801987924168 | scalar |
| 15 | Latest Quarter Assets/ Liabilities | 1.402474007052394 | scalar |
| 16 | Current 3 year EPS 10 years Av Growth | 1.741491799053041 | scalar |
| 17 | Current 3 year EPS 10 years Av Growth Direction | P | scalar |
| 18 | Current 3 year Revenue 10 years Av Growth | 0.6980893876899186 | scalar |
| 19 | Current TBV per Share | 5.782815049403183 | scalar |
| 20 | Current TBV/Price | 0.02088940884081632 | scalar |
| 21 | Current Dividend Rate | 1.08 | scalar |
| 22 | Current Dividend Yield | 0.003901311274067117 | scalar |
| 23 | Dividend Policy Satisfied | Yes | scalar |
| 24 | Expected Return Price Plus Dividends - Given Current Price | -0.2124157702387417 | scalar |
| 25 | Expected Return Price Plus Dividends - Given Max Entry Price | -0.1671158664960853 | scalar |
| 26 | ROCE | 0.3778733541373605 | scalar |
| 27 | ROCE Fiscal Year | 0.3103264939135567 | scalar |
| 28 | ROCE 5 Fiscal Years | 0.318106236071891 | scalar |
| 29 | ROCE 10 Fiscal Years | 0.2633332586522313 | scalar |
| 30 | Approximate Residual Earnings Value | 67.40230496741884 | scalar |
| 31 | Extrapolated Price Plus Dividends | 25.42045191727559 | scalar |
| 32 | Current Total Debt to (EBITDA 3 Year Average) | 0.8319518099642423 | scalar |
| 33 | Current Funds from Operations 10 Year Growth Direction | N | scalar |
| 34 | Current Debt to Gross Book Value Ratio | 0.1982986453302871 | scalar |
| 35 | Current Gross Book Value | 427189 | scalar |
| 36 | EPS Latest Fiscal Year | 7.464996043072248 | scalar |
| 37 | EPS Current Yield | 0.02696599372565202 | scalar |
| 38 | EPS Growth Direction Last Decade | P | scalar |
| 39 | EPS Growth Last Decade | 0.124735977490416 | scalar |
| 40 | Retained Earnings Average | -0.1636181959084042 | scalar |
| 41 | Book Value per Share Growth per Year | -0.1792924070372372 | scalar |
| 42 | ROE Average | 1.095797481703121 | scalar |
| 43 | Latest Owners Earnings to Equity (Fiscal Year) | 1.505336823403361 | scalar |
| 44 | Latest Owners Earnings per Share (Fiscal Year) | 7.397217264607786 | scalar |
| 45 | Dividends Since | 2012-08-16 00:00:00 | scalar |
| 46 | Current E10 | 5.577242073364912 | scalar |
| 47 | Current PE10 | 49.63564363147329 | scalar |
| 48 | Current Max PE10 to Enter (Lowest PE10 or 7PE10) | 28.37382487175449 | scalar |
| 49 | Expected Return @ Current Price | -0.1847226574965062 | scalar |
| 50 | % Shares to sell to recoup FV @ 1st Exit price | 1.226576464064699 | scalar |
| 51 | High Price in 10 years | 286.19 | scalar |
| 52 | Low Price in 10 years | 22.585 | scalar |
| 53 | SNOA (Scaled Net Operating Assets) | 0.330641205986817 | scalar |
| 54 | ROA10 | 0.2153282528169929 | scalar |
| 55 | ROC10 | 1.975737794966297 | scalar |
| 56 | CFOA | 2.313504831816148 | scalar |
| 57 | Number of Consecutive Positive Growth Margins | 25 | scalar |
| 58 | Profit Margin Growth | 0.0204984257214369 | scalar |
| 59 | Profit Margin Stability | 11.80488078337277 | scalar |
| 60 | P_FS | 1 | scalar |
| 61 | Current Enterprise Value (not-diluted) | 4004016.76148 | scalar |
| 62 | Current Market Capitalization | 4065900.76148 | scalar |
| 63 | EBIT TTM | 147366 | scalar |
| 64 | EBIT 5 year average | 124930.6 | scalar |
| 65 | EBIT TTM/EV | 0.03680454123412043 | scalar |
| 66 | EBIT 5 year average/EV | 0.03120131793699636 | scalar |
| 67 | Debt/Total Assets | 0.2282810807314825 | scalar |
| 68 | ROC Greenblatt | 2.940498044536675 | scalar |
| 69 | WACC | 0.122078 | scalar |
| 70 | ROC - WACC | 2.818420044536675 | scalar |
| 71 | Current FFO10 | None | scalar |
| 72 | Current PFFO10 | None | scalar |
| 73 | Current Book Value Per Share | 7.231557680824763 | scalar |
| 74 | Price/Book Value Per Share | None | scalar |
| 75 | Non-Performing Assets | None | scalar |
| 76 | Tier 1 Common Equity Ratio | None | scalar |
| 77 | Tier 1 Capital Ratio | None | scalar |
| 78 | Basel III Total Capital Ratio Fully Loaded | None | scalar |
| 79 | Efficiency Ratio | None | scalar |
| 80 | Net Interest Margin TTM | None | scalar |
| 81 | Non-Performing Assets Growth QOQ | None | scalar |
| 82 | Non-Performing Assets to Total Assets | None | scalar |
| 83 | ROE | 0.277751171460499 | scalar |
| 84 | Total Assets | 371082 | scalar |
| 85 | Six Month Price Change | 0.02476493669948909 | scalar |
| 86 | Gross Margin Fiscal Year | 0.4690516410716045 | scalar |
| 87 | Gross Margin TTM | 0.4786240535882794 | scalar |
| 88 | Operating Margin Fiscal Year | 0.3197079976259188 | scalar |
| 89 | Operating Margin 10 Fiscal Years | 0.2833827532985992 | scalar |
| 90 | Operating Margin TTM | 0.3264339605087697 | scalar |
| 91 | Cash Conversion Fiscal Year | 0.8908490313364879 | scalar |
| 92 | Cash Conversion TTM | 1.041093208239853 | scalar |
| 93 | Interest Coverage Ratio Fiscal Year | inf | scalar |
| 94 | Interest Coverage Ratio TTM | None | scalar |
| 95 | Current Graham Instrinsic Value | 291.5370204928446 | scalar |
| 96 | Graham Instrinsic Value in 7 Years | 454.3694346271823 | scalar |
| 97 | Graham Expected Annualized Return | 0.07335227081235085 | scalar |
| 98 | Six Month Price Change Rank | 1 | scalar |
| 99 | EBIT TTM/EV Rank | 1 | scalar |
| 100 | ROC - WACC Rank | 1 | scalar |
| 101 | Final Score | 2 | scalar |
| 102 | P_SNOA | 1 | scalar |
| 103 | P_ROA10 | 1 | scalar |
| 104 | P_ROC10 | 1 | scalar |
| 105 | P_CFOA10 | 1 | scalar |
| 106 | P_MG | 1 | scalar |
| 107 | P_MS | 1 | scalar |
| 108 | Maximum Margin | 1 | scalar |
| 109 | P_MM | 1 | scalar |
| 110 | Franchise Power | 1 | scalar |
| 111 | Quality_FPFS | 1 | scalar |

## AAPL Industrial Template (brief)
- File: `AAPL 2026 Q2 - Industrial Template v27.6.xlsx`
- Sheets (24): first 20 = ['Balance Sheet - Standardized', 'BS%', 'Income - GAAP', 'IS%', 'Cash Flow - Standardized', 'CF%', 'FCF', 'Last Quarter BS Standardized', 'Last Quarter IS Standardized', 'Last Quarter CF Standardized', 'Last Quarter BS As Reported', 'Last Quarter IS As Reported', 'Last Quarter CF As Reported', 'DividendHelper', 'Inputs', 'IC & NOPAT & ROIC ', 'Tax', 'Leases', 'R&D', 'All Ratios']
- All sheets: ['Balance Sheet - Standardized', 'BS%', 'Income - GAAP', 'IS%', 'Cash Flow - Standardized', 'CF%', 'FCF', 'Last Quarter BS Standardized', 'Last Quarter IS Standardized', 'Last Quarter CF Standardized', 'Last Quarter BS As Reported', 'Last Quarter IS As Reported', 'Last Quarter CF As Reported', 'DividendHelper', 'Inputs', 'IC & NOPAT & ROIC ', 'Tax', 'Leases', 'R&D', 'All Ratios', 'Final Metrics', 'Expected Returns & Buybacks', 'Enterprise Value', 'Template Version']
- Income-style: True; Balance-style: True; Cash-flow-style: True

## Parser recommendations
- Two sheets only: <TICKER> (proprietary long form) + Summary (1 header + 1 data row).
- Ticker sheet layout:
-   row1: title (e.g. 'AAPL US Equity' in col B)
-   rows ~2-12: scalar key-value in cols A/B (company meta, live price, sector, EV, next earnings)
-   blank rows
-   'date' row: quarterly period end dates across columns B..
-   'Fiscal Quarter' row: e.g. '2001 Q1'
-   many metric rows: col A = metric label, B.. = quarterly values (~100 cols / ~25 years)
-   'Fiscal Year' row appears mid/late aligning annual bins
-   additional current/derived scalar metrics (narrow A/B) interspersed or after
-   large trailing block (~3900 rows) with numeric indices in col A — appears to be a transposed daily/auxiliary matrix; IGNORE for metric catalog
- Summary sheet: identical 111-column schema across companies; one row of current scalars (overlaps ticker-sheet meta + derived scores).

### Suggested `CustomRunData`
```json
{
  "summary": "dict[str, Any] keyed by exact Summary header",
  "meta": "dict from ticker top KV",
  "periods_quarterly": "list[date|str] from date row",
  "periods_fiscal_quarter": "list[str] from Fiscal Quarter row",
  "periods_fiscal_year": "list[str|int] from Fiscal Year row",
  "series": "dict[str, list[Optional[float]]] keyed by metric label",
  "scalars_ticker": "dict for narrow post/mid series A/B fields",
  "ignore": "numeric-index trailer rows"
}
```