# Credits

## Photographs

The destination photographs in `web/public/img` come from Wikimedia Commons and are used under their
Creative Commons licences. They were resized to 500 px wide.

| Option | Photograph | Author | Licence |
|---|---|---|---|
| Goa | [Palolem Beach, south Goa](https://commons.wikimedia.org/wiki/File:Palolem_Beach,_south_Goa.jpg) | Mahabalaindia | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| Dubai | [Dubai Marina Skyline](https://commons.wikimedia.org/wiki/File:Dubai_Marina_Skyline_93.jpg) | Khanshahab06 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| Udaipur | [Pichola lake sunset](https://commons.wikimedia.org/wiki/File:Pichola_lake_sunset.JPG) | Arjuncm3 | [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0) |
| Manali | [Solang Valley, Manali](https://commons.wikimedia.org/wiki/File:Solang_Valley,_Manali.jpg) | Vikas Choudhary | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| Bali | [Tegallalang Rice Terraces](https://commons.wikimedia.org/wiki/File:Tegallalang_Rice_Terraces_Bali_1.jpg) | Philip Nalangan | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0) |
| Jaipur | [Hawa Mahal in Jaipur](https://commons.wikimedia.org/wiki/File:Hawa_Mahal_in_Jaipur_India.jpg) | Wander-earth | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| Munnar | [Munnar tea](https://commons.wikimedia.org/wiki/File:Munnar_tea_in_2024.jpg) | Dharaniyakumar | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0) |
| Srinagar | [Dal Lake with houseboats and shikaras](https://commons.wikimedia.org/wiki/File:View_of_Dal_Lake_with_Houseboats_and_Shikaras.jpg) | Vishalmgs | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| Phuket | [Patong Beach](https://commons.wikimedia.org/wiki/File:Patong_Beach_(1).jpg) | Wolfgang Holzem | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| Singapore | [Skyline, Marina Bay](https://commons.wikimedia.org/wiki/File:Skyline,_Marina_Bay,_Singapur,_2023-08-17,_DD_20.jpg) | Diego Delso | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |
| Bangkok | [Wat Arun and the Royal Barge Procession](https://commons.wikimedia.org/wiki/File:Wat_Arun_Ratchawararam_and_the_Royal_Barge_Procession.jpg) | Tee-12838 | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0) |

## Fonts

[Schibsted Grotesk](https://fonts.google.com/specimen/Schibsted+Grotesk) and
[JetBrains Mono](https://fonts.google.com/specimen/JetBrains+Mono), both under the SIL Open Font Licence,
loaded from Google Fonts.

## Methods

* Quantile regression with gradient-boosted trees: [LightGBM](https://github.com/microsoft/LightGBM).
* Conformalized quantile regression: Romano, Patterson and Candès, *Conformalized Quantile Regression*, NeurIPS 2019.
* CVaR as a linear programme: Rockafellar and Uryasev, *Optimization of Conditional Value-at-Risk*, Journal of Risk, 2000.
* Mixed-integer solving: [Google OR-Tools](https://developers.google.com/optimization) with [SCIP](https://www.scipopt.org).
