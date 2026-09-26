package com.Agent.javabackend.Config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.tomcat.servlet.TomcatServletWebServerFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

import java.time.Duration;

@Configuration
public class Config {
    @Bean
    public TomcatServletWebServerFactory tomcatServletWebServerFactory() {
        TomcatServletWebServerFactory factory = new TomcatServletWebServerFactory();
        /*
         * 当前 Windows/JDK 环境创建 NIO Selector 的内部 loopback Pipe 会失败。
         * 显式使用 Tomcat NIO2 协议，绕开 NioEndpoint 的 Selector/Pipe 初始化。
         */
        factory.setProtocol("org.apache.coyote.http11.Http11Nio2Protocol");
        return factory;
    }

    @Bean
    public RestClient agentRestClient(@Value("${agent-service.base-url}") String baseUrl,
                                      @Value("${agent-service.internal-token}") String token,
                                      @Value("${agent-service.connect-timeout-ms:3000}") long connectTimeoutMs,
                                      @Value("${agent-service.read-timeout-ms:30000}") long readTimeoutMs){
        /*
         * Spring Boot 4 默认可能使用 JDK HttpClient。
         * 当前本地 JDK 24 环境初始化该客户端时会尝试建立内部 loopback
         * selector 通道并失败，因此这里显式使用基于 HttpURLConnection
         * 的请求工厂，避免 Java 进程启动阶段就依赖 JDK HttpClient。
         */
        SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
        requestFactory.setConnectTimeout(Duration.ofMillis(connectTimeoutMs));
        requestFactory.setReadTimeout(Duration.ofMillis(readTimeoutMs));

        RestClient.Builder builder = RestClient.builder()
                .baseUrl(baseUrl)
                .requestFactory(requestFactory);

        if (!token.isBlank()) {
            builder.defaultHeader("X-Service-Token", token);
        }

        return builder.build();
    }
}
