#!/usr/bin/env python3
"""
ทดสอบระบบตรวจจับไฟตกแบบใหม่
"""

import sys
sys.path.append('.')

from app.services.ups_service import _human_status

def test_power_failure_scenarios():
    """ทดสอบสถานการณ์ต่างๆ ของการตรวจจับไฟตก"""
    
    print("🔍 ทดสอบระบบตรวจจับไฟตก")
    print("=" * 50)
    
    # สถานการณ์ที่ 1: ไฟปกติ
    scenario1 = {
        "input": {"L1V": 220, "L2V": 220, "L3V": 220},
        "output": {"L1V": 220, "L2V": 220, "L3V": 220}
    }
    status1 = _human_status(scenario1)
    print(f"📊 สถานการณ์ 1 - ไฟปกติ:")
    print(f"   Input: L1={scenario1['input']['L1V']}V, L2={scenario1['input']['L2V']}V, L3={scenario1['input']['L3V']}V")
    print(f"   Output: L1={scenario1['output']['L1V']}V, L2={scenario1['output']['L2V']}V, L3={scenario1['output']['L3V']}V")
    print(f"   ✅ สถานะ: {status1}")
    print()
    
    # สถานการณ์ที่ 2: ไฟตกสนิท (input = 0)
    scenario2 = {
        "input": {"L1V": 0, "L2V": 0, "L3V": 0},
        "output": {"L1V": 220, "L2V": 220, "L3V": 220}
    }
    status2 = _human_status(scenario2)
    print(f"📊 สถานการณ์ 2 - ไฟตกสนิท:")
    print(f"   Input: L1={scenario2['input']['L1V']}V, L2={scenario2['input']['L2V']}V, L3={scenario2['input']['L3V']}V")
    print(f"   Output: L1={scenario2['output']['L1V']}V, L2={scenario2['output']['L2V']}V, L3={scenario2['output']['L3V']}V")
    print(f"   ⚠️  สถานะ: {status2}")
    print()
    
    # สถานการณ์ที่ 3: ไฟตกบางส่วน (L1 < 180V)
    scenario3 = {
        "input": {"L1V": 150, "L2V": 220, "L3V": 220},
        "output": {"L1V": 220, "L2V": 220, "L3V": 220}
    }
    status3 = _human_status(scenario3)
    print(f"📊 สถานการณ์ 3 - ไฟตกบางส่วน (L1 ต่ำ):")
    print(f"   Input: L1={scenario3['input']['L1V']}V, L2={scenario3['input']['L2V']}V, L3={scenario3['input']['L3V']}V")
    print(f"   Output: L1={scenario3['output']['L1V']}V, L2={scenario3['output']['L2V']}V, L3={scenario3['output']['L3V']}V")
    print(f"   ⚠️  สถานะ: {status3}")
    print()
    
    # สถานการณ์ที่ 4: ไฟตกหลายเฟส
    scenario4 = {
        "input": {"L1V": 160, "L2V": 170, "L3V": 220},
        "output": {"L1V": 220, "L2V": 220, "L3V": 220}
    }
    status4 = _human_status(scenario4)
    print(f"📊 สถานการณ์ 4 - ไฟตกหลายเฟส:")
    print(f"   Input: L1={scenario4['input']['L1V']}V, L2={scenario4['input']['L2V']}V, L3={scenario4['input']['L3V']}V")
    print(f"   Output: L1={scenario4['output']['L1V']}V, L2={scenario4['output']['L2V']}V, L3={scenario4['output']['L3V']}V")
    print(f"   ⚠️  สถานะ: {status4}")
    print()
    
    # สถานการณ์ที่ 5: UPS ปิด
    scenario5 = {
        "input": {"L1V": 0, "L2V": 0, "L3V": 0},
        "output": {"L1V": 0, "L2V": 0, "L3V": 0}
    }
    status5 = _human_status(scenario5)
    print(f"📊 สถานการณ์ 5 - UPS ปิด:")
    print(f"   Input: L1={scenario5['input']['L1V']}V, L2={scenario5['input']['L2V']}V, L3={scenario5['input']['L3V']}V")
    print(f"   Output: L1={scenario5['output']['L1V']}V, L2={scenario5['output']['L2V']}V, L3={scenario5['output']['L3V']}V")
    print(f"   ❌ สถานะ: {status5}")
    print()
    
    # สถานการณ์ที่ 6: ไฟต่ำเล็กน้อย (ยังไม่ถึงเกณฑ์ไฟตก)
    scenario6 = {
        "input": {"L1V": 190, "L2V": 195, "L3V": 200},
        "output": {"L1V": 220, "L2V": 220, "L3V": 220}
    }
    status6 = _human_status(scenario6)
    print(f"📊 สถานการณ์ 6 - ไฟต่ำเล็กน้อย (ยังไม่ถึงเกณฑ์):")
    print(f"   Input: L1={scenario6['input']['L1V']}V, L2={scenario6['input']['L2V']}V, L3={scenario6['input']['L3V']}V")
    print(f"   Output: L1={scenario6['output']['L1V']}V, L2={scenario6['output']['L2V']}V, L3={scenario6['output']['L3V']}V")
    print(f"   ✅ สถานะ: {status6}")
    print()
    
    print("🎯 สรุปเกณฑ์การตรวจจับไฟตก:")
    print("   • Online: Input voltage ทุกเฟส ≥ 180V และ Output > 0")
    print("   • Powerfail: Input voltage เฟสใดเฟสหนึ่ง 0 < voltage < 180V หรือ Input = 0 แต่ Output > 0")
    print("   • Offline: Output voltage = 0 (UPS ปิดสนิท)")

if __name__ == "__main__":
    test_power_failure_scenarios()