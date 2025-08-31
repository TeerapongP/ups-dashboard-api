# SNMP Client Module
import asyncio
from typing import Dict, List, Optional, Any
from pysnmp.hlapi import (
    getCmd,
    SnmpEngine,
    CommunityData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
)


class SNMPClient:
    """SNMP client for UPS monitoring"""
    
    def __init__(self):
        self._ensure_event_loop()
    
    def _ensure_event_loop(self):
        """Ensure asyncio event loop exists"""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    
    def _create_target(self, ip: str, timeout: float, retries: int) -> UdpTransportTarget:
        """Create SNMP target"""
        return UdpTransportTarget((ip, 161), timeout=timeout, retries=retries)
    
    def _create_community(self, community: str, version: str = "2c") -> CommunityData:
        """Create SNMP community data"""
        mp_model = 0 if version.lower() in ("1", "v1") else 1
        return CommunityData(community, mpModel=mp_model)
    
    def get_single(
        self, 
        ip: str, 
        community: str, 
        oid: str, 
        timeout: float = 1.2, 
        retries: int = 0,
        version: str = "2c"
    ) -> Optional[str]:
        """Get single OID value"""
        if not oid:
            return None
            
        try:
            comm_obj = self._create_community(community, version)
            target = self._create_target(ip, timeout, retries)
            
            iterator = getCmd(
                SnmpEngine(),
                comm_obj,
                target,
                ContextData(),
                ObjectType(ObjectIdentity(oid)),
            )
            
            error_indication, error_status, error_index, var_binds = next(iterator)
            
            if error_indication or error_status:
                return None
                
            value = var_binds[0][1]
            raw_value = value.prettyPrint() if hasattr(value, "prettyPrint") else str(value)
            
            # Check for "No Such" responses
            if raw_value.lower().startswith(("no such", "nosuch")):
                return None
                
            return raw_value
            
        except Exception:
            return None
    
    def get_multiple(
        self, 
        ip: str, 
        community: str, 
        oids: List[str], 
        timeout: float = 1.2, 
        retries: int = 0,
        version: str = "2c"
    ) -> Dict[str, Optional[str]]:
        """Get multiple OID values in a single request"""
        if not oids:
            return {}
            
        try:
            comm_obj = self._create_community(community, version)
            target = self._create_target(ip, timeout, retries)
            
            iterator = getCmd(
                SnmpEngine(),
                comm_obj,
                target,
                ContextData(),
                *[ObjectType(ObjectIdentity(oid)) for oid in oids]
            )
            
            error_indication, error_status, error_index, var_binds = next(iterator)
            
            if error_indication or error_status:
                return {oid: None for oid in oids}
            
            result = {}
            for var_bind in var_binds:
                oid_str = str(var_bind[0])
                value = var_bind[1]
                raw_value = value.prettyPrint() if hasattr(value, "prettyPrint") else str(value)
                
                # Check for "No Such" responses
                if raw_value.lower().startswith(("no such", "nosuch")):
                    result[oid_str] = None
                else:
                    result[oid_str] = raw_value
                    
            return result
            
        except Exception:
            return {oid: None for oid in oids}


# Global SNMP client instance
snmp_client = SNMPClient()