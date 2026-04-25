-- ============================================================
-- Migration: Remove Vanna Training Data (2026-04-25)
-- ============================================================
-- Reason: Replaced by direct SQL tool, no more Vanna pre-training needed
-- This migration removes the vanna_training_data table

-- Step 1: Drop trigger first
DROP TRIGGER IF EXISTS update_vanna_training_data_updated_at ON vanna_training_data;

-- Step 2: Drop table
DROP TABLE IF EXISTS vanna_training_data;

-- Step 3: Remove from init_complete.sql notice
-- (Manual step: remove lines 1293 from init_complete.sql)
