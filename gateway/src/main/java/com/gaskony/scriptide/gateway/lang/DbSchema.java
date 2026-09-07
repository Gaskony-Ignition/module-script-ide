package com.gaskony.scriptide.gateway.lang;

import java.util.List;

/**
 * What {@link LanguageServer} needs to offer live database-schema completion
 * inside a SQL string literal — Ectobox borrowing #3,
 * {@code DatabaseCompletionHelper.getColumnCompletions}
 * (docs/ECTOBOX-BORROWINGS.md §3).
 *
 * <p>A pure interface, deliberately: {@link LanguageServer} depends on this
 * and never on JDBC or the Ignition datasource SDK directly, so it stays
 * unit-testable with a fake and all SDK/JDBC contact stays isolated in
 * {@link SdkDbSchema}. Every method answers NAMES only — a connection's own
 * name, a table's name, a column's name — never a row of data.</p>
 *
 * <p>The call that triggers a completion never names a datasource (a bare
 * {@code system.db.runPrepQuery(sql, args)} does not say which connection it
 * will run against until the third argument is typed, if it ever is), so
 * {@link LanguageServer} asks every method here across EVERY configured
 * datasource and lets {@code detail} say which connection each answer came
 * from, rather than guessing one.</p>
 */
public interface DbSchema {

    /** Configured datasource (database connection) names. */
    List<String> datasources();

    /** Table and view names in one datasource. */
    List<String> tables(String datasource);

    /** Column names of one table in one datasource. */
    List<String> columns(String datasource, String table);
}
