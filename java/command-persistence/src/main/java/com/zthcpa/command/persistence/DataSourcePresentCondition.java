package com.zthcpa.command.persistence;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

import javax.sql.DataSource;

final class DataSourcePresentCondition implements Condition {
    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        if (context.getBeanFactory() == null) {
            return false;
        }
        return context.getBeanFactory().getBeanNamesForType(DataSource.class).length > 0;
    }
}
