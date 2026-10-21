package com.Agent.javabackend.Config;

import org.apache.ibatis.type.BaseTypeHandler;
import org.apache.ibatis.type.JdbcType;

import java.sql.CallableStatement;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;

/** SQLite 将时间保存为 ISO-8601 文本；该处理器负责与 Java 时间对象互转。 */
public class SqliteOffsetDateTimeTypeHandler extends BaseTypeHandler<OffsetDateTime> {
    @Override
    public void setNonNullParameter(PreparedStatement ps, int i, OffsetDateTime parameter,
                                    JdbcType jdbcType) throws SQLException {
        ps.setString(i, parameter.withOffsetSameInstant(ZoneOffset.UTC).toString());
    }

    @Override
    public OffsetDateTime getNullableResult(ResultSet rs, String columnName) throws SQLException {
        return parse(rs.getString(columnName));
    }

    @Override
    public OffsetDateTime getNullableResult(ResultSet rs, int columnIndex) throws SQLException {
        return parse(rs.getString(columnIndex));
    }

    @Override
    public OffsetDateTime getNullableResult(CallableStatement cs, int columnIndex) throws SQLException {
        return parse(cs.getString(columnIndex));
    }

    private OffsetDateTime parse(String value) {
        return value == null ? null : OffsetDateTime.parse(value);
    }
}
