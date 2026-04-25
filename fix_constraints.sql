-- Add missing UNIQUE constraints for ON CONFLICT support

-- revenue_breakdown: unique by company, year, segment_name, segment_type
ALTER TABLE revenue_breakdown 
ADD CONSTRAINT revenue_breakdown_company_year_segment_unique 
UNIQUE (company_id, year, segment_name, segment_type);

-- shareholding_structure: unique by company, year, shareholder_name
ALTER TABLE shareholding_structure
ADD CONSTRAINT shareholding_structure_unique 
UNIQUE (company_id, year, shareholder_name);

-- market_data: unique by company, year, fiscal_period
ALTER TABLE market_data
ADD CONSTRAINT market_data_unique 
UNIQUE (company_id, year, fiscal_period);

-- entity_relations: unique by source, target, relation_type
ALTER TABLE entity_relations
ADD CONSTRAINT entity_relations_unique 
UNIQUE (source_company_id, target_company_id, relation_type);

-- document_companies: already has unique constraint, but let's verify
-- document_companies_document_id_company_id_key already exists

-- artifact_relations: unique by source, target, relation_type
ALTER TABLE artifact_relations
ADD CONSTRAINT artifact_relations_unique 
UNIQUE (source_artifact_id, target_artifact_id, relation_type);

-- review_queue: unique by document_id, table_name (for deduplication)
ALTER TABLE review_queue
ADD CONSTRAINT review_queue_unique 
UNIQUE (document_id, table_name, issue_type);
