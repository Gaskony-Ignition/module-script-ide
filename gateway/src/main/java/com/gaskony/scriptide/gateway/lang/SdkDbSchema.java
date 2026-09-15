package com.gaskony.scriptide.gateway.lang;

import com.inductiveautomation.ignition.gateway.datasource.Datasource;
import com.inductiveautomation.ignition.gateway.datasource.DatasourceManager;
import com.inductiveautomation.ignition.gateway.datasource.SRConnection;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.sql.DatabaseMetaData;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Executor;

/**
 * {@link DbSchema} backed by the real {@link DatasourceManager} and JDBC
 * {@link DatabaseMetaData}.
 *
 * <p>Every method opens a JDBC connection, so every method is cached (see
 * {@link TtlCache}) and NEVER on the thread that asked for a completion — a
 * keystroke typed inside a SQL string must not wait on a database round trip.
 * A cache miss schedules the read on {@code refreshExecutor} and answers
 * empty for THAT keystroke; the next completion request for the same key
 * sees whatever the background read produced.</p>
 *
 * <p>Table and column NAMES only, never a row of data — see {@link DbSchema}'s
 * own Javadoc on why every table/every datasource is asked rather than one
 * guessed connection. {@link #tables} asks for both {@code TABLE} and
 * {@code VIEW}, because a view answers a query exactly like a table does and
 * is how people actually write SQL against one.</p>
 */
public final class SdkDbSchema implements DbSchema {

    private static final Logger logger = LoggerFactory.getLogger(SdkDbSchema.class);

    /** Schema changes far less often than a tag tree, hence the longer TTL. */
    private static final long SCHEMA_TTL_MILLIS = 300_000;

    private static final int MAX_CACHE_ENTRIES = 200;

    /** Bound on how many tables/columns one completion request offers. */
    private static final int MAX_RESULTS = 500;

    private static final String[] TABLE_TYPES = {"TABLE", "VIEW"};

    private static final String DATASOURCES_KEY = "datasources";

    private final DatasourceManager datasourceManager;
    private final TtlCache<List<String>> datasourcesCache;
    private final TtlCache<List<String>> tablesCache;
    private final TtlCache<List<String>> columnsCache;

    public SdkDbSchema(DatasourceManager datasourceManager, Executor refreshExecutor) {
        this.datasourceManager = datasourceManager;
        // Cap of 1: there is exactly one datasources() answer per gateway.
        this.datasourcesCache = new TtlCache<>(SCHEMA_TTL_MILLIS, 1, System::currentTimeMillis, refreshExecutor);
        this.tablesCache =
            new TtlCache<>(SCHEMA_TTL_MILLIS, MAX_CACHE_ENTRIES, System::currentTimeMillis, refreshExecutor);
        this.columnsCache =
            new TtlCache<>(SCHEMA_TTL_MILLIS, MAX_CACHE_ENTRIES, System::currentTimeMillis, refreshExecutor);
    }

    @Override
    public List<String> datasources() {
        return datasourcesCache.get(DATASOURCES_KEY, this::loadDatasources).orElse(List.of());
    }

    private List<String> loadDatasources() {
        List<String> names = new ArrayList<>();
        for (Datasource ds : datasourceManager.getDatasources()) {
            names.add(ds.getName());
        }
        return names;
    }

    @Override
    public List<String> tables(String datasource) {
        return tablesCache.get(datasource, () -> loadTables(datasource)).orElse(List.of());
    }

    private List<String> loadTables(String datasource) {
        List<String> names = new ArrayList<>();
        try (SRConnection connection = datasourceManager.getConnection(datasource)) {
            DatabaseMetaData meta = connection.getMetaData();
            try (ResultSet rs = meta.getTables(null, null, "%", TABLE_TYPES)) {
                while (rs.next() && names.size() < MAX_RESULTS) {
                    String name = rs.getString("TABLE_NAME");
                    if (name != null) {
                        names.add(name);
                    }
                }
            }
        } catch (SQLException | RuntimeException e) {
            // Background thread, nothing synchronously waiting - see the
            // equivalent note in SdkTagBrowser.
            logger.debug("Table list failed for completion, datasource='{}': {}", datasource, e.toString());
        }
        return names;
    }

    @Override
    public List<String> columns(String datasource, String table) {
        // "." can appear in neither a datasource name nor a table name in
        // isolation the way this key needs it to be unambiguous, but since
        // both are also independently used as map keys of their OWN caches
        // (tablesCache keyed on datasource alone), a collision here would
        // only ever merge two columns() lookups - never cross into tables()
        // or datasources(). Good enough for a cache key, not a security
        // boundary.
        String key = datasource + '.' + table;
        return columnsCache.get(key, () -> loadColumns(datasource, table)).orElse(List.of());
    }

    private List<String> loadColumns(String datasource, String table) {
        List<String> names = new ArrayList<>();
        try (SRConnection connection = datasourceManager.getConnection(datasource)) {
            DatabaseMetaData meta = connection.getMetaData();
            try (ResultSet rs = meta.getColumns(null, null, table, "%")) {
                while (rs.next() && names.size() < MAX_RESULTS) {
                    String name = rs.getString("COLUMN_NAME");
                    if (name != null) {
                        names.add(name);
                    }
                }
            }
        } catch (SQLException | RuntimeException e) {
            logger.debug("Column list failed for completion, datasource='{}' table='{}': {}",
                datasource, table, e.toString());
        }
        return names;
    }
}
