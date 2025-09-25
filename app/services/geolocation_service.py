# backEnd/app/services/geolocation_service.py

import requests
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class GeolocationService:
    """Servicio para obtener geolocalización basada en IP"""

    @staticmethod
    def get_location_from_ip(ip_address: str) -> Dict[str, Optional[str]]:
        """
        Obtiene información de geolocalización desde una dirección IP.

        Args:
            ip_address: Dirección IP a consultar

        Returns:
            Dict con pais, ciudad, region o valores None si hay error
        """

        # Valores por defecto
        location_data = {
            "pais": None,
            "ciudad": None,
            "region": None
        }

        # No procesar IPs locales/privadas
        if GeolocationService._is_private_ip(ip_address):
            logger.info(f"IP privada detectada: {ip_address}, saltando geolocalización")
            location_data.update({
                "pais": "Local",
                "ciudad": "Red Local",
                "region": "Privada"
            })
            return location_data

        try:
            # Hacer request a ipapi.co (1000 requests gratis por día)
            response = requests.get(
                f"http://ipapi.co/{ip_address}/json/",
                timeout=5  # 5 segundos de timeout
            )

            if response.status_code == 200:
                data = response.json()

                # Verificar si hay errores en la respuesta
                if data.get("error"):
                    logger.warning(f"Error en API de geolocalización: {data.get('reason', 'Unknown')}")
                    return location_data

                # Extraer datos de ubicación
                location_data = {
                    "pais": data.get("country_name"),
                    "ciudad": data.get("city"),
                    "region": data.get("region")
                }

                logger.info(f"Geolocalización exitosa para IP {ip_address}: {location_data}")
                return location_data

            else:
                logger.warning(f"Error HTTP en geolocalización: {response.status_code}")

        except requests.exceptions.Timeout:
            logger.warning(f"Timeout en geolocalización para IP: {ip_address}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Error de conexión en geolocalización para IP: {ip_address}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Error en request de geolocalización: {str(e)}")
        except Exception as e:
            logger.error(f"Error inesperado en geolocalización: {str(e)}")

        return location_data

    @staticmethod
    def _is_private_ip(ip_address: str) -> bool:
        """
        Verifica si una IP es privada/local.

        Args:
            ip_address: IP a verificar

        Returns:
            True si es IP privada, False en caso contrario
        """
        try:
            import ipaddress
            ip = ipaddress.ip_address(ip_address)
            return ip.is_private or ip.is_loopback or ip.is_link_local
        except ValueError:
            # Si no es una IP válida, asumir que es privada por seguridad
            return True

    @staticmethod
    def get_location_sync(ip_address: str) -> Dict[str, Optional[str]]:
        """
        Wrapper síncrono para obtener ubicación.
        Alias para get_location_from_ip para mantener compatibilidad.
        """
        return GeolocationService.get_location_from_ip(ip_address)