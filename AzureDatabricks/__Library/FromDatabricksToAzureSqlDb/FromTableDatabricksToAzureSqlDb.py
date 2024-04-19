# Databricks notebook source
# DBTITLE 1,Information
# MAGIC %md
# MAGIC Stage table data from Databricks to Azure SQL DB
# MAGIC
# MAGIC Required additional libraries:
# MAGIC - None

# COMMAND ----------

# Parameters
try:
    # Source database e.g. lehdetdw
    __SOURCE_DATABASE = dbutils.widgets.get("SOURCE_DATABASE")
  
    # Source table.g. f_tilaus
    __SOURCE_TABLE = dbutils.widgets.get("SOURCE_TABLE")
  
    # Source track date columns e.g. __ModifiedDatetimeUTC
    __SOURCE_TRACK_DATE_COLUMN = "__ModifiedDatetimeUTC"
    try:
        __SOURCE_TRACK_DATE_COLUMN = dbutils.widgets.get("SOURCE_TRACK_DATE_COLUMN")
    except:
        print("Using default source track column: " + __SOURCE_TRACK_DATE_COLUMN)
   
    # Target process datetime log path e.g. analytics/datawarehouse/address/log/
    __TARGET_LOG_PATH = dbutils.widgets.get("TARGET_LOG_PATH")
  
    # Columns to extract e.g. * or AddressID, AddressLine1, AddressLine2, City, StateProvince, CountryRegion, PostalCode, rowguid, ModifiedDate
    __EXTRACT_COLUMNS = dbutils.widgets.get("EXTRACT_COLUMNS")
  
    # Table name with schema e.g. stg.X_adventureworkslt_address
    __TABLE_NAME = dbutils.widgets.get("TABLE_NAME")
    
    # Include previous. Use "True" or "False"
    # True = ArchiveDatetimeUTC >= lastProcessDatetimeUTC
    # False = ArchiveDatetimeUTC > lastProcessDatetimeUTC
    __INCLUDE_PREVIOUS = "False"
    try:
        __INCLUDE_PREVIOUS = dbutils.widgets.get("INCLUDE_PREVIOUS")
    except:
        print("Using default include previous: " + __INCLUDE_PREVIOUS)
  
    # Delta day count e.g. get data newer than 3 days since the last processing date
    __DELTA_DAY_COUNT = 0
    try:
        __DELTA_DAY_COUNT = dbutils.widgets.get("DELTA_DAY_COUNT")
    except:
        print("Using default delta day count: " + str(__DELTA_DAY_COUNT))
    
except:
    raise Exception("Required parameter(s) missing")

# COMMAND ----------

# Import
import sys
from pyspark.sql.utils import AnalysisException
from pyspark.sql.functions import lit, max
from datetime import datetime, timedelta

# Configuration
__SECRET_SCOPE = "KeyVault"
__SECRET_NAME_DATA_LAKE_APP_CLIENT_ID = "App-databricks-id"
__SECRET_NAME_DATA_LAKE_APP_CLIENT_SECRET = "App-databricks-secret"
__SECRET_NAME_DATA_LAKE_APP_CLIENT_TENANT_ID = "App-databricks-tenant-id"
__SECRET_NAME_SQL_JDBC_CONNECTION_STRING = "Datawarehouse-JDBC-connection-string"
__DATA_LAKE_NAME = dbutils.secrets.get(scope = __SECRET_SCOPE, key = "Storage-Name")

__TARGET_LOG_PATH = "abfss://synapse@" + __DATA_LAKE_NAME + ".dfs.core.windows.net/" + __TARGET_LOG_PATH + "/processDatetime/"

# Data lake authentication
spark.conf.set("fs.azure.account.auth.type." + __DATA_LAKE_NAME + ".dfs.core.windows.net", "OAuth")
spark.conf.set("fs.azure.account.oauth.provider.type." + __DATA_LAKE_NAME + ".dfs.core.windows.net", "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider")
spark.conf.set("fs.azure.account.oauth2.client.id." + __DATA_LAKE_NAME + ".dfs.core.windows.net", dbutils.secrets.get(scope = __SECRET_SCOPE, key = __SECRET_NAME_DATA_LAKE_APP_CLIENT_ID))
spark.conf.set("fs.azure.account.oauth2.client.secret." + __DATA_LAKE_NAME + ".dfs.core.windows.net", dbutils.secrets.get(scope = __SECRET_SCOPE, key = __SECRET_NAME_DATA_LAKE_APP_CLIENT_SECRET))
spark.conf.set("fs.azure.account.oauth2.client.endpoint." + __DATA_LAKE_NAME + ".dfs.core.windows.net", "https://login.microsoftonline.com/" + dbutils.secrets.get(scope = __SECRET_SCOPE, key = __SECRET_NAME_DATA_LAKE_APP_CLIENT_TENANT_ID) + "/oauth2/token")

# In Spark 3.1, loading and saving of timestamps from/to parquet files fails if the timestamps are before 1900-01-01 00:00:00Z, and loaded (saved) as the INT96 type. 
# In Spark 3.0, the actions don’t fail but might lead to shifting of the input timestamps due to rebasing from/to Julian to/from Proleptic Gregorian calendar. 
# To restore the behavior before Spark 3.1, you can set spark.sql.parquet.int96RebaseModeInRead or/and spark.sql.legacy.parquet.int96RebaseModeInWrite to LEGACY.
spark.conf.set("spark.sql.parquet.int96RebaseModeInWrite", "LEGACY")
spark.conf.set("spark.sql.parquet.int96RebaseModeInRead", "LEGACY")

# Azure SQL authentication
__SQL_JDBC = dbutils.secrets.get(scope = __SECRET_SCOPE, key = __SECRET_NAME_SQL_JDBC_CONNECTION_STRING)

# COMMAND ----------

# Get process datetimes
lastProcessDatetimeUTC = None
try:
    dfProcessDatetimes = spark.read.format("delta").load(__TARGET_LOG_PATH)
    lastProcessDatetimeUTC = dfProcessDatetimes.select(max(dfProcessDatetimes.ProcessDatetime)).collect()[0][0] - timedelta(days = int(__DELTA_DAY_COUNT))
    print("Using existing log with date: " + str(lastProcessDatetimeUTC))
except AnalysisException as ex:
    # Initiliaze delta as it did not exist
    dfProcessDatetimes = spark.sql("SELECT CAST('1900-01-01' AS timestamp) AS ProcessDatetime")
    dfProcessDatetimes.write.format("delta").mode("append").option("mergeSchema", "true").save(__TARGET_LOG_PATH)
    lastProcessDatetimeUTC = dfProcessDatetimes.select(max(dfProcessDatetimes.ProcessDatetime)).collect()[0][0]
    print("Initiliazed log with date: " + str(lastProcessDatetimeUTC))
except Exception as ex:
    print("Could not read log")
    print(ex)
    raise

# COMMAND ----------

queryBeginsDatetimeUTC = datetime.utcnow()
dfAnalytics = spark.sql("SELECT * FROM " + __SOURCE_DATABASE  + "." + __SOURCE_TABLE + " WHERE `" + __SOURCE_TRACK_DATE_COLUMN + "` " + (__INCLUDE_PREVIOUS == "True" and ">=" or ">") + " CAST('" + str(lastProcessDatetimeUTC) + "' AS timestamp)")
dfAnalytics.write.mode("overwrite").jdbc(url=__SQL_JDBC, table=__TABLE_NAME)

# COMMAND ----------

# Check if anything was done
maxDatetimeUTC = spark.sql("""
  SELECT MAX(`""" + __SOURCE_TRACK_DATE_COLUMN + """`) AS `maxDatetimeUTC` 
  FROM   """ + __SOURCE_DATABASE  + """.""" + __SOURCE_TABLE + """ 
  WHERE `""" + __SOURCE_TRACK_DATE_COLUMN + """` >= CAST('""" + str(lastProcessDatetimeUTC) + """' AS timestamp) AND
        `""" + __SOURCE_TRACK_DATE_COLUMN + """` <= CAST('""" + str(queryBeginsDatetimeUTC) + """' AS timestamp)""").collect()[0][0]

if maxDatetimeUTC:
    # Save max. archive datetime to target process datetime log
    dfProcessDatetime = spark.sql("SELECT CAST('" + str(maxDatetimeUTC) + "' AS timestamp) AS ProcessDatetime")
    dfProcessDatetime.write.format("delta") \
                         .mode("append") \
                         .save(__TARGET_LOG_PATH)

# COMMAND ----------

# Return success
dbutils.notebook.exit(True)
