# UPS Service Module
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from app.services.ups_config import UPS_DEVICES, DEFAULT_CONFIG
from app.services.snmp_client import snmp_client
from app.api.routes.data_utils import OIDResolver, DataProcessor
from app.services.ups_cache import ups_cache


class UPSService:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=10)
    
    def get_ups_data(
    self, 
        ip: str, 
        timeout: float = None, 
        retries: int = None, 
        use_cache: bool = True,
        cache_ttl: float = None
    ) -> Dict[str, Any]:
        
        # Get device configuration
        device_config = UPS_DEVICES.get(ip)
        if not device_config:
            raise ValueError(f"No configuration found for UPS at {ip}")
        
        # Use defaults if not specified
        timeout = timeout or DEFAULT_CONFIG["timeout"]
        retries = retries or DEFAULT_CONFIG["retries"]
        cache_ttl = cache_ttl or DEFAULT_CONFIG["cache_ttl"]
        
        # Check cache first
        if use_cache:
            cached_data = ups_cache.get(ip, cache_ttl)
            if cached_data:
                return cached_data
        
        # Collect fresh data
        data = self._collect_ups_data(ip, device_config, timeout, retries)
        
        # Cache the result
        if use_cache:
            ups_cache.set(ip, data)
        
        return data
    
    def get_all_ups_data(
        self, 
        timeout: float = None, 
        retries: int = None,
        use_cache: bool = True,
        cache_ttl: float = None
    ) -> List[Dict[str, Any]]:
        """Get data for all configured UPS devices"""
        
        # Use thread pool for concurrent data collection
        futures = []
        for ip in UPS_DEVICES.keys():
            future = self.executor.submit(
                self.get_ups_data, ip, timeout, retries, use_cache, cache_ttl
            )
            futures.append((ip, future))
        
        results = []
        for ip, future in futures:
            try:
                data = future.result(timeout=10)  # 10 second timeout per device
                results.append(data)
            except Exception as e:
                # Log error and continue with other devices
                print(f"Error collecting data from UPS {ip}: {e}")
                # Add error entry
                results.append({
                    "id": f"UPS_{ip.replace('.', '_')}",
                    "ip": ip,
                    "status": "Error",
                    "error": str(e)
                })
        
        return results
    
    def _collect_ups_data(
        self, 
        ip: str, 
        device_config: Dict[str, Any], 
        timeout: float, 
        retries: int
    ) -> Dict[str, Any]:
        """Collect data from a single UPS device"""
        
        # Get OID configuration
        oid_config = device_config.get("oids", {})
        resolver = OIDResolver(oid_config)
        
        # Get all required OIDs
        all_oids = resolver.get_all_oids()
        
        # Collect SNMP data
        community = device_config.get("community", DEFAULT_CONFIG["community"])
        version = device_config.get("snmp_version", DEFAULT_CONFIG["snmp_version"])
        
        oid_values = snmp_client.get_multiple(
            ip=ip,
            community=community,
            oids=all_oids,
            timeout=timeout,
            retries=retries,
            version=version
        )
        
        # Process the data
        processor = DataProcessor(resolver)
        return processor.process_ups_data(ip, oid_values, device_config)
    
    def get_device_list(self) -> List[Dict[str, str]]:
        """Get list of configured UPS devices"""
        devices = []
        for ip, config in UPS_DEVICES.items():
            devices.append({
                "ip": ip,
                "brand": config.get("brand", "Unknown"),
                "model": config.get("model", "Unknown"),
                "location": config.get("location", "Unknown")
            })
        return devices
    
    def clear_cache(self) -> None:
        ups_cache.clear()
    
    def remove_from_cache(self, ip: str) -> None:
        ups_cache.remove(ip)


# Global service instance
ups_service = UPSService()