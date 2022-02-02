# skola24 extract schooldays for current semester

Based on TekniskSupport/home-assistant-skola24-to-ical

Configuration example:
```yaml
- platform: skola24
  school: Ankeborgsskolan
  class: 9A
  url: ankeborg.skola24.se
  name: mysensor
```

Configuration example using a personal identification number:
```yaml
- platform: skola24
  school: Ankeborgsskolan
  pin: 991231-1234
  url: ankeborg.skola24.se
  name: mysensor

```
