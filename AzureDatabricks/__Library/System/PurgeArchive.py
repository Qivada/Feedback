# Databricks notebook source
from datetime import datetime, timedelta
import pandas as pd
import uuid
import time

# Configuration
__SECRET_SCOPE = "KeyVault"
__SECRET_NAME_DATA_LAKE_APP_CLIENT_ID = "App-databricks-id"
__SECRET_NAME_DATA_LAKE_APP_CLIENT_SECRET = "App-databricks-secret"
__SECRET_NAME_DATA_LAKE_APP_CLIENT_TENANT_ID = "App-databricks-tenant-id"
__DATA_LAKE_NAME = dbutils.secrets.get(scope = __SECRET_SCOPE, key = "Storage-Name")
__ARCHIVE_TARGET_DATABASE = "Qivada_ADA"

# Data lake authentication
spark.conf.set("fs.azure.account.auth.type." + __DATA_LAKE_NAME + ".dfs.core.windows.net", "OAuth")
spark.conf.set("fs.azure.account.oauth.provider.type." + __DATA_LAKE_NAME + ".dfs.core.windows.net", "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider")
spark.conf.set("fs.azure.account.oauth2.client.id." + __DATA_LAKE_NAME + ".dfs.core.windows.net", dbutils.secrets.get(scope = __SECRET_SCOPE, key = __SECRET_NAME_DATA_LAKE_APP_CLIENT_ID))
spark.conf.set("fs.azure.account.oauth2.client.secret." + __DATA_LAKE_NAME + ".dfs.core.windows.net", dbutils.secrets.get(scope = __SECRET_SCOPE, key = __SECRET_NAME_DATA_LAKE_APP_CLIENT_SECRET))
spark.conf.set("fs.azure.account.oauth2.client.endpoint." + __DATA_LAKE_NAME + ".dfs.core.windows.net", "https://login.microsoftonline.com/" + dbutils.secrets.get(scope = __SECRET_SCOPE, key = __SECRET_NAME_DATA_LAKE_APP_CLIENT_TENANT_ID) + "/oauth2/token")

# Purge filter
tableNameStartsWith = []
tableNameStartsWith.append('archive_')

purgeOlderThanNDays = 31
startPurgeFromTime = datetime.today() - timedelta(days=purgeOlderThanNDays)
keepLastOfAnyYear: bool = True
keepLastOfAnyMonth: bool = True
keepLastOfAnyWeek: bool = True
keepLastOfAnyDay: bool = True

totalBytesToPurge = 0
totalBytesToRetain = 0
totalBytesPurged = 0

isDryRun: bool = True

# COMMAND ----------

def convert_size_bytes(size_bytes):
    """
    Converts a size in bytes to a human readable string using SI units.
    """
    import math
    import sys

    if size_bytes is None:
        return "0B"

    if not isinstance(size_bytes, int):
        size_bytes = sys.getsizeof(size_bytes)

    if size_bytes == 0:
        return "0B"

    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])

# COMMAND ----------

def purgeFromArchiveTable(fullyQualifiedName):
    global totalBytesToPurge
    global totalBytesToRetain
    global totalBytesPurged 
    global isDryRun

    print('Purge from archive table: {table}'.format(table = fullyQualifiedName))

    dfArchiveRecordsToPurge = spark.sql("""
    select  extendedArchiveData.`ArchiveDatetimeUTC`,
            extendedArchiveData.`OriginalStagingFileSize`,
            extendedArchiveData.`ArchiveFilePath`,
            extendedArchiveData.`IsPurged`,
            case when not (
                extendedArchiveData.`IsLastOfYearRowNbr` == {keepLastOfAnyYear} or
                extendedArchiveData.`IsLastOfMonthRowNbr` == {keepLastOfAnyMonth} or
                extendedArchiveData.`IsLastOfWeekRowNbr` == {keepLastOfAnyWeek} or
                extendedArchiveData.`IsLastOfDayRowNbr` == {keepLastOfAnyDay}
            ) then true else false end as `IsToBePurged`
    from    (
                select  archiveData.*,
                        row_number() over(partition by archiveData.`ArchiveYearUTC` order by archiveData.`ArchiveDatetimeUTC` desc) as `IsLastOfYearRowNbr`,
                        row_number() over(partition by archiveData.`ArchiveYearUTC`, archiveData.`ArchiveMonthUTC` order by archiveData.`ArchiveDatetimeUTC` desc) as `IsLastOfMonthRowNbr`,
                        row_number() over(partition by archiveData.`ArchiveYearUTC`, archiveData.`ArchiveWeekUTC` order by archiveData.`ArchiveDatetimeUTC` desc) as `IsLastOfWeekRowNbr`,
                        row_number() over(partition by archiveData.`ArchiveYearUTC`, archiveData.`ArchiveMonthUTC`, archiveData.`ArchiveDayUTC` order by archiveData.`ArchiveDatetimeUTC` desc) as `IsLastOfDayRowNbr`
                from   (
                        select  `ArchiveDatetimeUTC`,
                                `ArchiveYearUTC`,
                                `ArchiveMonthUTC`,
                                weekofyear(`ArchiveDatetimeUTC`) as `ArchiveWeekUTC`, 
                                `ArchiveDayUTC`,
                                `OriginalStagingFileSize`,       
                                `IsPurged`,
                                `PurgeDatetimeUTC`,
                                `ArchiveFilePath`
                        from    {archiveTable} 
                        where   `ArchiveDatetimeUTC` <= '{timestamp}'
                    ) as archiveData
            ) as extendedArchiveData
    """.format(archiveTable = fullyQualifiedName, \
               timestamp = startTime, \
               keepLastOfAnyYear = (1 if keepLastOfAnyYear == True else 0), \
               keepLastOfAnyMonth = (1 if keepLastOfAnyMonth == True else 0), \
               keepLastOfAnyWeek = (1 if keepLastOfAnyWeek == True else 0), \
               keepLastOfAnyDay = (1 if keepLastOfAnyDay == True else 0)))

    bytesToPurge = dfArchiveRecordsToPurge.filter("IsPurged == false and IsToBePurged == true").groupBy().sum("OriginalStagingFileSize").collect()[0][0]
    if bytesToPurge:
        totalBytesToPurge = totalBytesToPurge + bytesToPurge

    bytesToRetain = dfArchiveRecordsToPurge.filter("IsPurged == false and IsToBePurged == false").groupBy().sum("OriginalStagingFileSize").collect()[0][0]
    if bytesToRetain:
        totalBytesToRetain = totalBytesToRetain + bytesToRetain

    bytesPurged = dfArchiveRecordsToPurge.filter("IsPurged == true").groupBy().sum("OriginalStagingFileSize").collect()[0][0]
    if bytesPurged:
        totalBytesPurged = totalBytesPurged + bytesPurged

    print('> Bytes to purge: {size}'.format(size = convert_size_bytes(bytesToPurge)))
    print('> Bytes to retain: {size}'.format(size = convert_size_bytes(bytesToRetain)))
    print('> Bytes already purged: {size}'.format(size = convert_size_bytes(bytesPurged)))

    if not isDryRun:   
        purgedArchiveLogEntries = None
        for archiveRecordToPurge in dfArchiveRecordsToPurge.filter("IsPurged == false and IsToBePurged == true").collect():
            try:            
                print('.', end = "") 
                dbutils.fs.rm(archiveRecordToPurge.ArchiveFilePath)

                if purgedArchiveLogEntries is None:
                    purgedArchiveLogEntries = []

                purgedArchiveLogEntries.append({
                'ArchiveDatetimeUTC': archiveRecordToPurge.ArchiveDatetimeUTC,
                'ArchiveFilePath': archiveRecordToPurge.ArchiveFilePath
                })
            except Exception as e:
                print('> Could not purge file: {archiveFilePath}: {message}'.format(archiveFilePath = archiveRecordToPurge.ArchiveFilePath, message = e))
                pass
    
        if purgedArchiveLogEntries:
            temporaryViewName = str(uuid.uuid4()).replace('-', '_')
            dfPurgedArchiveLogEntries = spark.createDataFrame(pd.DataFrame(purgedArchiveLogEntries))
            dfPurgedArchiveLogEntries.createOrReplaceTempView(temporaryViewName)
            sql = """
                    UPDATE {archiveTable} AS T1
                    SET    `IsPurged` = True,
                        `PurgeDatetimeUTC` = current_timestamp()
                    WHERE  EXISTS (
                                SELECT 1 AS Exists
                                FROM   {temporaryView}
                                WHERE  T1.`ArchiveFilePath` = `ArchiveFilePath` AND
                                    T1.`ArchiveDatetimeUTC` = `ArchiveDatetimeUTC`
                            )
                    """.format(archiveTable = fullyQualifiedName, \
                                temporaryView = temporaryViewName)
            spark.sql(sql)
            print(" [Commit]")


# COMMAND ----------

startTime = spark.sql("SELECT CAST('{timestamp}' AS timestamp) AS ArchiveDatetimeUTC".format(timestamp = startPurgeFromTime)).collect()[0][0]
print('Start purge from timestamp: {timestamp}'.format(timestamp = startTime))
print('Keep last of any:')
print('> Year: {case}'.format(case = keepLastOfAnyYear))
print('  > Month: {case}'.format(case = keepLastOfAnyMonth))
print('    > Week: {case}'.format(case = keepLastOfAnyWeek))
print('      > Day: {case}'.format(case = keepLastOfAnyDay))
print('Archive filter:')
for tableNameFilter in tableNameStartsWith:
    print('> {name}'.format(name = tableNameFilter))

if not isDryRun:
    print('')
    print('WARNING! Purge operation is configured as active. Waiting 30 seconds before continuing')
    print('> Interrupt notebook now if you wish to abort the purge operation', end='')
    for second in reversed(range(30)):
        char = (' ' + str(second)) if second <= 10 else '.'
        print(char, end='')
        time.sleep(1)
    print('')
else:
    print('')
    print('NOTE! Purge operation is configured as dry run. Archive purge will not happen')

dfTables = spark.sql('SHOW tables from `{archive_database}`'.format(archive_database = __ARCHIVE_TARGET_DATABASE))
for table in dfTables.collect():
    if any(table.tableName.startswith(tableFilter) for tableFilter in tableNameStartsWith):
        purgeFromArchiveTable("`{database}`.`{table}`".format(database = table.database, table = table.tableName))


print('')
print('Archive purge summary: ')
print('> Total bytes to purge: {size}'.format(size = convert_size_bytes(totalBytesToPurge)))
print('> Total bytes to retain: {size}'.format(size = convert_size_bytes(totalBytesToRetain)))
print('> Total bytes already purged: {size}'.format(size = convert_size_bytes(totalBytesPurged)))
