package com.Agent.javabackend.Config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

/**
 * local 模式允许浏览和绑定目录的根位置，以及本机请求保护配置。
 *
 * 根目录只能由维护者通过配置或环境变量提供；用户不能通过请求增加根位置。
 */
@Data
@Component
@ConfigurationProperties(prefix = "local-directory")
public class LocalDirectoryProperties {
    /** 服务端允许的根位置别名。 */
    private List<Root> roots = new ArrayList<>();
    /** local 前端来源，例如 http://127.0.0.1:5173。 */
    private List<String> allowedOrigins = new ArrayList<>(
            List.of("http://127.0.0.1:5173", "http://localhost:5173"));
    /** Host 头允许的主机名，不含端口。 */
    private List<String> trustedHosts = new ArrayList<>(
            List.of("localhost", "127.0.0.1", "::1"));
    /** 可选的本机访问凭据；设置后所有实际请求都必须带 X-Local-Access-Token。 */
    private String accessToken = "";
    /** 游标签名密钥；留空时每次启动生成随机密钥。 */
    private String cursorSecret = "";
    private int maxPageSize = 200;
    private int maxScanEntries = 10_000;
    private long scanTimeoutMs = 2_000;

    @Data
    public static class Root {
        private String rootId;
        private String name;
        private String path;
    }
}
