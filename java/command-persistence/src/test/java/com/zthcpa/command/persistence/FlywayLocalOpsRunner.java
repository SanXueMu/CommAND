package com.zthcpa.command.persistence;

import org.flywaydb.core.Flyway;

/**
 * 本地/演练环境 Flyway 运维入口：显式 baseline 与 migrate，不进入生产启动路径。
 *
 * 用法：
 *   COMMAND_DB_URL / COMMAND_DB_USER / COMMAND_DB_PASSWORD 控制目标库（默认本地 pglab command_dev）
 *   参数：baseline | migrate | validate | info
 */
public final class FlywayLocalOpsRunner {

    public static void main(String[] args) {
        String url = env("COMMAND_DB_URL", "jdbc:postgresql://localhost:5432/command_dev");
        String user = env("COMMAND_DB_USER", "command_dev");
        String password = env("COMMAND_DB_PASSWORD", "root");
        String command = args.length > 0 ? args[0] : "info";

        Flyway flyway = Flyway.configure()
                .dataSource(url, user, password)
                .locations("classpath:db/migration")
                .baselineVersion("22")
                .baselineDescription("command_existing_python_schema")
                .baselineOnMigrate(false)
                .validateOnMigrate(true)
                .outOfOrder(false)
                .cleanDisabled(true)
                .load();

        switch (command) {
            case "baseline" -> flyway.baseline();
            case "migrate" -> flyway.migrate();
            case "validate" -> flyway.validate();
            default -> flyway.info();
        }
    }

    private static String env(String name, String fallback) {
        String value = System.getenv(name);
        return (value == null || value.isBlank()) ? fallback : value;
    }

    private FlywayLocalOpsRunner() {
    }
}
