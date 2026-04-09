"""
Entity Resolver for Company Name Resolution

Provides company entity resolution, search, and listing functions
for the financial analysis tools.

Functions:
- resolve_company(name) - Resolve company name to standard entity
- search_companies(query) - Search companies by keyword
- list_all_companies() - List all known companies
"""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from loguru import logger
import asyncpg
import os


@dataclass
class CompanyEntity:
    """Company entity with resolved information"""
    id: int
    name_en: str
    name_zh: Optional[str]
    stock_code: Optional[str]
    industry: Optional[str]
    sector: Optional[str]
    aliases_en: List[str]
    aliases_zh: List[str]


class EntityResolver:
    """
    Company entity resolver using PostgreSQL database.
    
    Resolves company names (CN/EN) to standard CompanyEntity objects.
    """
    
    def __init__(self, db_url: str = None):
        """
        Initialize entity resolver.
        
        Args:
            db_url: PostgreSQL connection URL
        """
        self.db_url = db_url or os.getenv(
            "DATABASE_URL",
            "postgresql://postgres:postgres_password_change_me@localhost:5433/annual_reports"
        )
        self._conn: Optional[asyncpg.Connection] = None
    
    async def connect(self):
        """Connect to database"""
        if not self._conn:
            self._conn = await asyncpg.connect(self.db_url)
            logger.info("✅ EntityResolver connected to database")
    
    async def close(self):
        """Close connection"""
        if self._conn:
            await self._conn.close()
            self._conn = None
    
    async def resolve_company_async(self, name: str) -> Optional[CompanyEntity]:
        """
        Resolve company name to standard entity (async version).
        
        Args:
            name: Company name (CN or EN, or stock code)
        
        Returns:
            CompanyEntity if found, None otherwise
        """
        await self.connect()
        
        try:
            # Try multiple matching strategies
            row = await self._conn.fetchrow(
                """
                SELECT id, name_en, name_zh, stock_code, industry, sector
                FROM companies
                WHERE stock_code = $1
                   OR name_en ILIKE $2
                   OR name_zh ILIKE $2
                   OR name_en ILIKE $3
                   OR name_zh ILIKE $3
                LIMIT 1
                """,
                name,  # Exact stock code match
                name,  # Exact name match
                f"%{name}%"  # Partial name match
            )
            
            if row:
                return CompanyEntity(
                    id=row['id'],
                    name_en=row['name_en'],
                    name_zh=row['name_zh'],
                    stock_code=row['stock_code'],
                    industry=row['industry'],
                    sector=row['sector'],
                    aliases_en=[row['name_en']] if row['name_en'] else [],
                    aliases_zh=[row['name_zh']] if row['name_zh'] else []
                )
            
            logger.warning(f"⚠️ Company not found: {name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Resolve company failed: {e}")
            return None
    
    async def search_companies_async(self, query: str, limit: int = 10) -> List[CompanyEntity]:
        """
        Search companies by keyword (async version).
        
        Args:
            query: Search keyword
            limit: Max results
        
        Returns:
            List of matching CompanyEntity
        """
        await self.connect()
        
        try:
            rows = await self._conn.fetch(
                """
                SELECT id, name_en, name_zh, stock_code, industry, sector
                FROM companies
                WHERE name_en ILIKE $1
                   OR name_zh ILIKE $1
                   OR stock_code ILIKE $1
                   OR industry ILIKE $1
                   OR sector ILIKE $1
                ORDER BY name_en
                LIMIT $2
                """,
                f"%{query}%",
                limit
            )
            
            return [
                CompanyEntity(
                    id=row['id'],
                    name_en=row['name_en'],
                    name_zh=row['name_zh'],
                    stock_code=row['stock_code'],
                    industry=row['industry'],
                    sector=row['sector'],
                    aliases_en=[row['name_en']] if row['name_en'] else [],
                    aliases_zh=[row['name_zh']] if row['name_zh'] else []
                )
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"❌ Search companies failed: {e}")
            return []
    
    async def list_all_companies_async(self) -> List[CompanyEntity]:
        """
        List all known companies (async version).
        
        Returns:
            List of all CompanyEntity
        """
        await self.connect()
        
        try:
            rows = await self._conn.fetch(
                """
                SELECT id, name_en, name_zh, stock_code, industry, sector
                FROM companies
                ORDER BY name_en
                """
            )
            
            return [
                CompanyEntity(
                    id=row['id'],
                    name_en=row['name_en'],
                    name_zh=row['name_zh'],
                    stock_code=row['stock_code'],
                    industry=row['industry'],
                    sector=row['sector'],
                    aliases_en=[row['name_en']] if row['name_en'] else [],
                    aliases_zh=[row['name_zh']] if row['name_zh'] else []
                )
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"❌ List companies failed: {e}")
            return []


# Global resolver instance
_resolver: Optional[EntityResolver] = None


def get_resolver() -> EntityResolver:
    """Get global resolver instance"""
    global _resolver
    if not _resolver:
        _resolver = EntityResolver()
    return _resolver


# Synchronous wrapper functions for use in financial.py
# These use asyncio.run() internally

import asyncio

def resolve_company(name: str) -> Optional[CompanyEntity]:
    """
    Resolve company name to standard entity (sync wrapper).
    
    Args:
        name: Company name (CN or EN, or stock code)
    
    Returns:
        CompanyEntity if found, None otherwise
    """
    resolver = get_resolver()
    try:
        # Try to run in existing event loop or create new one
        try:
            loop = asyncio.get_running_loop()
            # If we're already in an async context, need to use different approach
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, 
                    resolver.resolve_company_async(name)
                )
                return future.result()
        except RuntimeError:
            # No running loop, create new one
            return asyncio.run(resolver.resolve_company_async(name))
    except Exception as e:
        logger.error(f"❌ resolve_company wrapper failed: {e}")
        return None


def search_companies(query: str, limit: int = 10) -> List[CompanyEntity]:
    """
    Search companies by keyword (sync wrapper).
    
    Args:
        query: Search keyword
        limit: Max results
    
    Returns:
        List of matching CompanyEntity
    """
    resolver = get_resolver()
    try:
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, 
                    resolver.search_companies_async(query, limit)
                )
                return future.result()
        except RuntimeError:
            return asyncio.run(resolver.search_companies_async(query, limit))
    except Exception as e:
        logger.error(f"❌ search_companies wrapper failed: {e}")
        return []


def list_all_companies() -> List[CompanyEntity]:
    """
    List all known companies (sync wrapper).
    
    Returns:
        List of all CompanyEntity
    """
    resolver = get_resolver()
    try:
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run, 
                    resolver.list_all_companies_async()
                )
                return future.result()
        except RuntimeError:
            return asyncio.run(resolver.list_all_companies_async())
    except Exception as e:
        logger.error(f"❌ list_all_companies wrapper failed: {e}")
        return []


# Test functions
if __name__ == "__main__":
    print("Testing Entity Resolver...\n")
    
    # Test 1: List all companies
    print("1. List All Companies:")
    companies = list_all_companies()
    print(f"   Found {len(companies)} companies")
    for c in companies[:5]:
        print(f"   - {c.name_en} ({c.stock_code}) - {c.industry}")
    
    # Test 2: Resolve company
    print("\n2. Resolve Company:")
    test_names = ["腾讯", "Alibaba", "0700.HK", "Tencent"]
    for name in test_names:
        entity = resolve_company(name)
        if entity:
            print(f"   ✓ '{name}' → {entity.name_en} ({entity.stock_code})")
        else:
            print(f"   ✗ '{name}' not found")
    
    # Test 3: Search companies
    print("\n3. Search Companies:")
    results = search_companies("Technology")
    print(f"   Found {len(results)} technology companies")
    for c in results[:3]:
        print(f"   - {c.name_en}")
    
    print("\n✅ Entity Resolver test complete!")