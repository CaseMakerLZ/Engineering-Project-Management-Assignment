package com.Agent.javabackend.Client;

import com.Agent.javabackend.exception.BaseException;
import com.Agent.javabackend.exception.ErrorCode;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import java.net.SocketTimeoutException;
import java.time.Duration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.springframework.test.web.client.ExpectedCount.once;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withStatus;

class PythonAgentClientTest {

    @Test
    void mapsPython404ToAgentRunNotFound() {
        TestFixture fixture = fixture();
        fixture.server.expect(once(), requestTo("http://python/api/internal/runs/missing"))
                .andExpect(method(HttpMethod.GET))
                .andRespond(withStatus(HttpStatus.NOT_FOUND));

        BaseException exception = assertThrows(
                BaseException.class,
                () -> fixture.client.getRun("missing")
        );

        assertEquals(ErrorCode.AGENT_RUN_NOT_FOUND, exception.getErrorCode());
        fixture.server.verify();
    }

    @Test
    void mapsPythonUnauthorizedToInternalServiceAuthFailure() {
        TestFixture fixture = fixture();
        fixture.server.expect(once(), requestTo("http://python/api/internal/health"))
                .andRespond(withStatus(HttpStatus.UNAUTHORIZED));

        BaseException exception = assertThrows(BaseException.class, fixture.client::health);

        assertEquals(ErrorCode.AGENT_SERVICE_AUTH_FAILED, exception.getErrorCode());
        fixture.server.verify();
    }

    @Test
    void mapsPython422ToInvalidArgument() {
        TestFixture fixture = fixture();
        fixture.server.expect(once(), requestTo("http://python/api/internal/runs"))
                .andRespond(withStatus(HttpStatus.UNPROCESSABLE_ENTITY));

        BaseException exception = assertThrows(
                BaseException.class,
                () -> fixture.client.createRun(new com.Agent.javabackend.dto.CreateRunRequest(null, "test"))
        );

        assertEquals(ErrorCode.INVALID_ARGUMENT, exception.getErrorCode());
        fixture.server.verify();
    }

    @Test
    void mapsUnexpectedPythonErrorToBadGatewayBusinessError() {
        TestFixture fixture = fixture();
        fixture.server.expect(once(), requestTo("http://python/api/internal/health"))
                .andRespond(withStatus(HttpStatus.INTERNAL_SERVER_ERROR));

        BaseException exception = assertThrows(BaseException.class, fixture.client::health);

        assertEquals(ErrorCode.AGENT_SERVICE_RESPONSE_ERROR, exception.getErrorCode());
        fixture.server.verify();
    }

    @Test
    void mapsReadTimeoutToGatewayTimeoutBusinessError() {
        RestClient restClient = RestClient.builder()
                .requestFactory(new TimeoutRequestFactory())
                .baseUrl("http://python")
                .build();
        PythonAgentClient client = new PythonAgentClient(restClient);

        BaseException exception = assertThrows(BaseException.class, client::health);

        assertEquals(ErrorCode.AGENT_SERVICE_TIMEOUT, exception.getErrorCode());
    }

    private TestFixture fixture() {
        RestClient.Builder builder = RestClient.builder().baseUrl("http://python");
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        return new TestFixture(new PythonAgentClient(builder.build()), server);
    }

    private record TestFixture(PythonAgentClient client, MockRestServiceServer server) {
    }

    private static final class TimeoutRequestFactory extends SimpleClientHttpRequestFactory {
        private TimeoutRequestFactory() {
            setConnectTimeout(Duration.ofMillis(50));
            setReadTimeout(Duration.ofMillis(50));
        }

        @Override
        protected void prepareConnection(java.net.HttpURLConnection connection, String httpMethod)
                throws java.io.IOException {
            throw new SocketTimeoutException("simulated timeout");
        }
    }
}
