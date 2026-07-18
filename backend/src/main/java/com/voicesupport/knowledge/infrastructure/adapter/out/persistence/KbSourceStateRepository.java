package com.voicesupport.knowledge.infrastructure.adapter.out.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface KbSourceStateRepository extends JpaRepository<KbSourceStateEntity, KbSourceStateId> {

    List<KbSourceStateEntity> findBySourceType(String sourceType);
}
