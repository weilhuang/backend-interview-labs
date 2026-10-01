package labs;

import labs.environment.VersionLedger;

/** 从仓库真源或带 SHA256 的独立课程快照读取镜像。 */
public final class Images {
    private Images() {}

    public static String mysql() {
        return VersionLedger.get("MYSQL_IMAGE");
    }
}
