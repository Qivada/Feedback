# ADA Integration Runtime
ADA Integration Runtime is required for running ADA work flows on on-premise side.

## Required outbound connections
1. Azure West Europe Service Bus IP range
   - Download current IP ranges from: https://www.microsoft.com/en-us/download/details.aspx?id=56519
   - See IP ranges from section "ServiceBus.WestEurope"
2. Port 443 TCP
   - Https port. TLS 1.2 is used for connection.
   - Ciphersuite of TLS 1.2 connection is determined from available chiphers from Windows Operating system ADA Integration Runtime is installed.

### Azure West Europe Service Bus IP range (2022-07-01)
```
{
    "name": "ServiceBus.WestEurope",
    "id": "ServiceBus.WestEurope",
    "properties": {
    "changeNumber": 6,
    "region": "westeurope",
    "regionId": 18,
    "platform": "Azure",
    "systemService": "AzureServiceBus",
    "addressPrefixes": [
        "13.69.64.64/29",
        "13.69.106.64/29",
        "13.69.111.64/26",
        "20.50.201.0/26",
        "20.86.92.0/25",
        "23.100.15.87/32",
        "40.68.127.68/32",
        "51.144.124.255/32",
        "52.166.127.37/32",
        "52.178.17.64/26",
        "52.232.119.191/32",
        "52.236.186.64/29",
        "65.52.128.246/32",
        "65.52.137.29/32",
        "2603:1020:206:1::220/123",
        "2603:1020:206:4::/120",
        "2603:1020:206:402::170/125",
        "2603:1020:206:802::150/125",
        "2603:1020:206:c02::150/125"
    ],
    "networkFeatures": [
        "API",
        "NSG"
    ]
}
```