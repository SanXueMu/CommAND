package com.zthcpa.command.runtime;

import org.springframework.boot.context.properties.ConfigurationProperties;

import java.time.Duration;

@ConfigurationProperties("command.clean.scheduler")
public class CleanSchedulerProperties {
    private boolean enabled;
    private String workerId;
    private String workerBaseUrl;
    private Duration pollInterval = Duration.ofSeconds(1);
    private Duration workerTimeout = Duration.ofSeconds(30);
    private Duration jobPollInterval = Duration.ofMillis(250);
    private Duration jobTimeout = Duration.ofMinutes(30);
    private Duration heartbeatInterval = Duration.ofSeconds(30);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getWorkerId() {
        return workerId;
    }

    public void setWorkerId(String workerId) {
        this.workerId = workerId;
    }

    public String getWorkerBaseUrl() {
        return workerBaseUrl;
    }

    public void setWorkerBaseUrl(String workerBaseUrl) {
        this.workerBaseUrl = workerBaseUrl;
    }

    public Duration getPollInterval() {
        return pollInterval;
    }

    public void setPollInterval(Duration pollInterval) {
        this.pollInterval = pollInterval;
    }

    public Duration getWorkerTimeout() {
        return workerTimeout;
    }

    public void setWorkerTimeout(Duration workerTimeout) {
        this.workerTimeout = workerTimeout;
    }

    public Duration getJobPollInterval() {
        return jobPollInterval;
    }

    public void setJobPollInterval(Duration jobPollInterval) {
        this.jobPollInterval = jobPollInterval;
    }

    public Duration getJobTimeout() {
        return jobTimeout;
    }

    public void setJobTimeout(Duration jobTimeout) {
        this.jobTimeout = jobTimeout;
    }

    public Duration getHeartbeatInterval() {
        return heartbeatInterval;
    }

    public void setHeartbeatInterval(Duration heartbeatInterval) {
        this.heartbeatInterval = heartbeatInterval;
    }
}
