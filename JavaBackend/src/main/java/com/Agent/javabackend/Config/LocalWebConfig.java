package com.Agent.javabackend.Config;

import com.Agent.javabackend.auth.LocalAccessGuard;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

/** local 模式只为本机目录接口增加访问保护与受限 CORS。 */
@Profile("local")
@Component
public class LocalWebConfig implements WebMvcConfigurer {
    private final LocalDirectoryProperties properties;

    public LocalWebConfig(LocalDirectoryProperties properties) {
        this.properties = properties;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new LocalAccessGuard(properties))
                .addPathPatterns("/api/local/**");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        if (properties.getAllowedOrigins() == null || properties.getAllowedOrigins().isEmpty()) {
            return;
        }
        registry.addMapping("/api/local/**")
                .allowedOrigins(properties.getAllowedOrigins().toArray(String[]::new))
                .allowedMethods("GET", "POST", "OPTIONS")
                .allowedHeaders("Content-Type", "Accept", LocalAccessGuard.TOKEN_HEADER)
                .maxAge(600);
    }
}
