"""
Utilities for Cloudinary image optimization.
"""
import cloudinary.api
import cloudinary.uploader


def get_optimized_image_url(image_url, width=800, quality='auto', format_type='auto'):
    """
    Transform Cloudinary URL for optimal delivery.
    
    Args:
        image_url: Original Cloudinary URL
        width: Image width in pixels (default: 800)
        quality: Auto quality (auto, 80, 90, etc.)
        format_type: Image format (auto, webp, jpg, etc.)
    
    Returns:
        Optimized Cloudinary URL
    """
    if not image_url:
        return image_url
    
    if 'res.cloudinary.com' not in image_url:
        return image_url
    
    # Build transformation string
    transformations = f'w_{width},f_{format_type},q_{quality},c_fill'
    
    # Insert transformation into URL
    import re
    match = re.search(r'(res\.cloudinary\.com/[^/]+/image/upload/)(.*)', image_url)
    
    if match:
        base = match.group(1)
        resource = match.group(2)
        return f"{base}{transformations}/{resource}"
    
    return image_url


def get_responsive_image_srcset(image_url, base_width=800):
    """
    Generate srcset for responsive images.
    
    Args:
        image_url: Original Cloudinary URL
        base_width: Base width for 1x density
    
    Returns:
        srcset string for img tag
    """
    if not image_url or 'res.cloudinary.com' not in image_url:
        return image_url
    
    import re
    match = re.search(r'(res\.cloudinary\.com/[^/]+/image/upload/)(.*)', image_url)
    
    if not match:
        return image_url
    
    base = match.group(1)
    resource = match.group(2)
    
    # Generate multiple sizes for responsive loading
    sizes = [
        (base_width, '1x'),
        (base_width * 2, '2x'),
        (base_width // 2, '0.5x'),
    ]
    
    srcset_parts = []
    for size, density in sizes:
        url = f"{base}w_{size},f_auto,q_auto,c_fill/{resource}"
        srcset_parts.append(f"{url} {density}")
    
    return ', '.join(srcset_parts)
