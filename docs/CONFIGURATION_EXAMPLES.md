# Configuration Examples

This page shows recommended settings for some known Swedish DSOs (distribution system operators) that use a peak-based capacity tariff (effekttariff).

> ⚠️ **Disclaimer:** The information in this table is compiled from publicly available tariff descriptions and may be incomplete, outdated, or inaccurate. Tariff models change over time and vary by customer segment, subscription level, and region. Always verify your exact tariff design directly with your DSO before relying on these values. The authors accept no responsibility for misconfigured integrations or incorrect cost calculations.

---

## How to use this table

- Find your DSO column.
- Fill in every setting that has a value shown. Settings shown as *(default)* are already correct out of the box — you only need to confirm them.
- Settings left blank should remain at their default.
- Your actual `price_per_kw` must come from your own invoice or DSO price list.

---

## DSO comparison

| Setting | | Ellevio | Göteborg Energi | Vattenfall Eldistribution | Tekniska verken — 5-peak model | Tekniska verken — 2-peak day/night ⚠️ | Jönköping Energi ⚠️ | Umeå Energi | Mälarenergi (Västerås) ⚠️ | Lerum Energi *(from Sep 2026)* |
|---|---|---|---|---|---|---|---|---|---|---|
| **Tariff design** | | Avg of top 3 daily peaks. Night 22–06 weighted at 50% every day including weekends. No seasonal restriction. | Avg of top 3 daily peaks. Helgfria vardagar 07–20. Nov–Mar only. Weekends and röda dagar = noll. | Avg of top 5 daily peaks. Helgfria vardagar 07–21. Nov–Mar only. Weekends and röda dagar = noll. | Avg of top 5 hourly peaks per month. Multiple peaks per day allowed. No weekday restriction stated. | Two separate capacity prices: one for daytime (06–23) peaks and one for night-time (23–06) peaks. **Requires two separate Peak Monitor instances.** ⚠️ | **Avg of the two highest peaks per day. This model is currently not supported by Peak Monitor.** ⚠️ | Avg of top 5 daily peaks. Weekdays 07–20, Nov–Mar only. | Two separate capacity prices for daytime and night-time peaks. **Requires two separate Peak Monitor instances.** ⚠️ | Avg of top 3 daily peaks. Helgfria vardagar 06–21. Nov–Mar only. |
| | | | | | | | | | | |
| **— Basic Setup —** | | | | | | | | | | |
| Sensor Resets Every Hour | | Depends on your meter | Depends on your meter | Depends on your meter | Depends on your meter | Depends on your meter | — | Depends on your meter | Depends on your meter | Depends on your meter |
| Number of Peaks | | `3` | `3` | `5` | `5` | `2` per instance | — | `5` | `2` per instance | `3` |
| Only One Peak Per Day | | ☑ Yes *(default)* | ☑ Yes *(default)* | ☑ Yes *(default)* | ☐ **No** | ☑ Yes *(default)* | — | ☑ Yes *(default)* | ☑ Yes *(default)* | ☑ Yes *(default)* |
| Price per kW | | *From your invoice* | *From your invoice* | *From your invoice* | *From your invoice* | *Daytime rate* / *Night rate* | — | *From your invoice* | *Daytime rate* / *Night rate* | *From your invoice* |
| Fixed Monthly Fee | | *From your invoice* | *From your invoice* | *From your invoice* | *From your invoice* | Split between instances | — | *From your invoice* | Split between instances | *From your invoice* |
| Active Months | | All *(default)* | `Nov Dec Jan Feb Mar` | `Nov Dec Jan Feb Mar` | All *(default)* | All *(default)* | — | `Nov Dec Jan Feb Mar` | All *(default)* | `Nov Dec Jan Feb Mar` |
| | | | | | | | | | | |
| **— Weekdays —** | | | | | | | | | | |
| Start Hour | | `6` *(default)* | `7` | `7` | `6` *(default)* | `6` (day) / `23` (night) | — | `7` | `6` (day) / `22` (night) | `6` *(default)* |
| End Hour | | `22` | `20` | `21` | `22` | `23` (day) / `6` (night) | — | `20` | `22` (day) / `6` (night) | `21` |
| | | | | | | | | | | |
| **— Weekends —** | | | | | | | | | | |
| Weekend Behaviour | | **Full tariff** ² | No tariff *(default)* | No tariff *(default)* | Full tariff | No tariff *(default)* | — | No tariff *(default)* | **Full tariff** | No tariff *(default)* |
| Weekend Start Hour | | `6` *(default)* | — | — | `6` *(default)* | — | — | — | `6` (day) / `22` (night) | — |
| Weekend End Hour | | `22` | — | — | `22` | — | — | — | `22` (day) / `6` (night) | — |
| | | | | | | | | | | |
| **— Holidays —** | | | | | | | | | | |
| Holiday Behaviour | | No tariff *(default)* | No tariff *(default)* | No tariff *(default)* | No tariff *(default)* | No tariff *(default)* | — | No tariff *(default)* | No tariff *(default)* | No tariff *(default)* |
| Define Holidays | | *(none)* ³ | Official holidays (röda dagar) ⁴ | Official + trettondagsafton + påskafton + midsommarafton + julafton + nyårsafton | Official holidays | Official holidays | — | Official + julafton + nyårsafton | Official holidays | Official + trettondagsafton + julafton + nyårsafton |
| | | | | | | | | | | |
| **— Periodic Reduced Tariff —** | | | | | | | | | | |
| Enable Daily Reduced Tariff | | ☑ **Yes** | ☐ No *(default)* | ☐ No *(default)* | ☐ No *(default)* | ☐ No *(default)* | — | ☐ No *(default)* | ☐ No *(default)* | ☐ No *(default)* |
| Also on Weekends | | ☑ **Yes** ⁵ | — | — | — | — | — | — | — | — |
| Reduced Start Hour | | `22` | — | — | — | — | — | — | — | — |
| Reduced End Hour | | `6` | — | — | — | — | — | — | — | — |
| | | | | | | | | | | |
| **— Advanced —** | | | | | | | | | | |
| Estimation Sensor | | — | — | — | — | — | — | — | — | — |
| External Reduce Sensor | | — | — | — | — | — | — | — | — | — |
| External Mute Sensor | | — | — | — | — | — | — | — | — | — |
| Reduced Factor | | `0.5` *(default)* ⁶ | — | — | — | — | — | — | — | — |
| Reset Value | | 500 *(default)* | 500 *(default)* | 500 *(default)* | 500 *(default)* | 500 *(default)* | — | 500 *(default)* | 500 *(default)* | 500 *(default)* |
| Output Unit | | *Your preference* | *Your preference* | *Your preference* | *Your preference* | *Your preference* | — | *Your preference* | *Your preference* | *Your preference* |

---

## ⚠️ Jönköping Energi — not currently supported

Jönköping Energi's model uses the average of the **two highest peaks per day** within each measurement hour. This is a fundamentally different calculation from the single daily-peak model that Peak Monitor implements and is currently not supported. Do not attempt to configure Peak Monitor for Jönköping Energi without first verifying that your specific contract uses a different, supported model.

---

## ⚠️ Tekniska verken — two-peak day/night model

Tekniska verken offer a second product where **two separate capacity prices** apply: one for daytime peaks (06–23) and one for night-time peaks (23–06). The daytime price and night-time price are different fixed SEK/kW rates — they are not a proportional reduction of the same price, so Peak Monitor's single `reduced_factor` cannot model this correctly within one instance.

**The solution is to run two separate Peak Monitor instances** — one for daytime and one for night-time:

| | Daytime instance | Night-time instance |
|---|---|---|
| Name | e.g. `Tekniska verken Dag` | e.g. `Tekniska verken Natt` |
| Number of Peaks | `2` | `2` |
| Active Start Hour | `6` | `23` |
| Active End Hour | `23` | `6` |
| Weekend Behaviour | No tariff | No tariff |
| Price per kW | Daytime rate | Night-time rate |

This requires the integration to be configured twice, and then assesed separetly or merged together outside th integration — you can add Peak Monitor more than once under Settings → Devices & Services.

**Rate adjustment:** Tekniska verken may update their day and night rates twice per year (winter/summer schedule change). Remember to update `price_per_kw` in both instances when this happens, or calculate an annual average yourself and accept the approximation.

---

## ⚠️ Mälarenergi — two-price day/night model

Mälarenergi's current effekttariff (new pricing model from January 2025) works similarly to the Tekniska verken day/night model: **two separate capacity prices** apply for daytime and night-time peaks. These two prices are not a simple percentage of each other, so Peak Monitor's single `reduced_factor` cannot model this correctly in one instance.

**The solution is to run two separate Peak Monitor instances** — one for daytime and one for night-time. Verify the exact hour boundaries and price levels from your own Mälarenergi price list, as these may vary by subscription tier.

| | Daytime instance | Night-time instance |
|---|---|---|
| Name | e.g. `Mälarenergi Dag` | e.g. `Mälarenergi Natt` |
| Number of Peaks | `2` | `2` |
| Active Start Hour | `6` | `22` |
| Active End Hour | `22` | `6` |
| Weekend Behaviour | Full tariff | Full tariff |
| Weekend Start Hour | `6` | `22` |
| Weekend End Hour | `22` | `6` |
| Holiday Behaviour | No tariff | No tariff |
| Define Holidays | Official holidays | Official holidays |
| Price per kW | Daytime rate | Night-time rate |

> Verify hour boundaries, weekend rules, and holiday exclusions directly against your current Mälarenergi contract and price list before deploying.

---

## Footnotes

**² Ellevio — Weekend Behaviour = Full tariff.** Ellevio does not differentiate between weekdays and weekends. Weekend daytime peaks count at full weight, exactly like weekday peaks. See the Ellevio notes section below for full explanation.

**³ Ellevio — No holidays.** Ellevio's published tariff does not exclude official holidays from peak measurement — the tariff runs every day of the year. Leave Define Holidays empty for a strict reading of the Ellevio model.

**⁴ Göteborg Energi — Official holidays (röda dagar).** The following Swedish public holidays are explicitly excluded: nyårsdagen, trettondag jul, långfredagen, annandag påsk, juldagen, and annandag jul. All of these are covered by the "Official holidays" option.

**⁵ Ellevio — "Also on Weekends" is essential.** Ellevio's 50% night weighting applies every night of the year, Saturday and Sunday included. Without this checkbox, weekend nights count at full weight.

**⁶ Ellevio — Reduced Factor = 0.5.** Ellevio's tariff states that consumption during 22:00–06:00 counts at 50% of actual consumption.

---

## Notes per DSO

### Ellevio
Peaks are tracked every day of the week at full weight during 06–22. Night hours 22–06 count at 50% weight every night including weekends. Set **Weekend Behaviour = Full tariff** so that weekend daytime is treated identically to weekday daytime. The **Also on Weekends** checkbox then ensures the reduced window also fires on Saturday and Sunday nights.

Ellevio's tariff does not exclude official holidays — leave Define Holidays empty.

Resulting states (every day of the week):
- 06:00–21:59 → **Active** (full weight)
- 22:00–05:59 → **Reduced** (50% weight)

### Göteborg Energi Elnät
Winter months only. Weekdays 07–20. The following Swedish public holidays (röda dagar) are explicitly excluded: nyårsdagen, trettondag jul, långfredagen, annandag påsk, juldagen, and annandag jul. Select **Official holidays** in Define Holidays — this covers all of these days.

### Vattenfall Eldistribution
Same structure as Göteborg Energi but 5 peaks and active until 21:00. In addition to official red days, enable the following holiday evenings in Define Holidays: trettondagsafton, påskafton, midsommarafton, julafton, and nyårsafton — these are listed as excluded days in Vattenfall's published tariff. Note that Vattenfall's effekttariff rollout started October 2025 with general rollout autumn 2026 — verify that you are on the effekttariff product.

### Tekniska verken (Linköping) — 5-peak model
Multiple peaks per day — the top 5 hourly peaks anywhere in the month count regardless of day. Disable *Only One Peak Per Day*. Weekends appear to be included (no weekday-only restriction stated in public sources — verify with your contract).

### Tekniska verken — day/night model
See the ⚠️ section above. Two separate instances required.

### Jönköping Energi
See the ⚠️ section above. This model uses the average of the two highest peaks per day, which is currently not supported by Peak Monitor.

### Umeå Energi
Five-peak winter model, weekdays 07–20. In addition to official red days, julafton and nyårsafton are excluded — enable these alongside the Official holidays option in Define Holidays.

### Mälarenergi (Västerås)
See the ⚠️ section above. Two separate instances required for the current pricing model (from January 2025). Verify your exact contract terms and current price list with Mälarenergi.

### Lerum Energi *(launches 1 September 2026)*
Effektavgift gäller 1 november till 31 mars under helgfria vardagar klockan 06:00–20:59. This is a clean winter-weekday model identical in structure to Göteborg Energi. Active hours 06–21 (hour 20 is the last measured hour). In addition to official holidays, trettondagsafton (January 5), julafton (December 24), and nyårsafton (December 31) should be excluded — enable these alongside the Official holidays option in Define Holidays.
