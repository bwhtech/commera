# Commera - Complete Setup Guide

This guide will walk you through setting up Commera from installation to publishing your first product on the website.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Initial Configuration](#initial-configuration)
4. [Creating Your First Product](#creating-your-first-product)
5. [Publishing to Website](#publishing-to-website)
6. [Accessing the Frontend](#accessing-the-frontend)
7. [Advanced Features](#advanced-features)
8. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before installing Commera, ensure you have the following:

### Required Apps
- **Frappe Framework** (v13 or higher)
- **ERPNext** (must be installed first)
- **Webshop** (dependency for Commera)
- **Payments** (for payment gateway integration)

### System Requirements
- Node.js and npm (for asset compilation)
- Python 3.8+
- Database: MariaDB/PostgreSQL

### ERPNext Setup Requirements
Before installing Commera, ensure these are configured in ERPNext:
- ✅ Company created and configured
- ✅ Default Warehouse created
- ✅ Price Lists created (e.g., "Standard Selling")
- ✅ Chart of Accounts configured
- ✅ At least one Item Attribute (e.g., "Color", "Size")

---

## Installation

### Quick Start with Demo Data

If you want to quickly test Commera with demo products, you have two options:

#### Option 1: Using Commera Settings (Recommended)

1. Navigate to: **Desk → Commera Ecommerce → Commera Settings**
2. Scroll to **Demo Data & Testing** section
3. Click **"Install Demo Data"** button
4. Wait for completion notification
5. Click **"Publish All Items to Website"** button if items don't show
6. Visit `https://your-site.com/en/products`

#### Option 2: Using Command Line

```bash
# After installing commera
bench --site your-site-name execute commera.install_summer_demo.install_summer_demo
```

This seeds the Summer storefront in the **company's own currency**, so finish the setup wizard first:
without a company, a default currency and a chart of accounts the seeder stops and says so.
SAR, INR and IDR get hand-picked local prices (`CURRENCY_PROFILES` in `commera/install_summer_demo.py`);
any other currency is converted from the dollar catalogue at the USD exchange rate, which needs a
Currency Exchange record (or ERPNext's live rate lookup) to exist.
The seeder is idempotent — run it as often as you like.

The company, its accounts and its currency are never changed. What the seeder does align is the system
default, all three price lists and every Item Price, and it restates the demo catalogue, the shipping
rule, the COD charge and the hero-slide copy at that currency's scale. A store whose company and price
list disagree cannot submit a single Sales Invoice, which is what makes this the setting to get right
before anything else.

#### Rebuilding a demo site from nothing

Five commands take you from an empty bench to a storefront that can complete a paid checkout:

```bash
SITE=ls-shop-sar.localhost

bench new-site $SITE --admin-password admin
bench --site $SITE install-app erpnext commera
bench --site $SITE execute frappe.desk.page.setup_wizard.setup_wizard.setup_complete --kwargs '{"args": {"language": "en", "country": "Saudi Arabia", "timezone": "Asia/Riyadh", "currency": "SAR", "company_name": "Lifestyle Demo", "company_abbr": "LSD", "chart_of_accounts": "Standard", "fy_start_date": "2026-01-01", "fy_end_date": "2026-12-31", "full_name": "Administrator", "email": "admin@example.com", "password": "admin"}}'
bench --site $SITE migrate
bench --site $SITE execute commera.install_summer_demo.install_summer_demo
```

Two things about that order are load-bearing:

- **`bench migrate` before the seeder.** `Shop Theme` records sync on migrate and not on install-app,
  so activating the Summer theme straight after install throws "Could not find Active Theme".
- **The setup wizard will log `MandatoryError: [Item Group, ...]: custom_displayname`.** commera makes
  that field mandatory, so ERPNext cannot insert its own stock groups. The wizard still completes and
  the storefront does not use those groups; the errors are noise.

**What Gets Created:**
- ✅ Item Attributes (Color, Size)
- ✅ Brands (Adidas, Nike, Puma, Lifestyle Store)
- ✅ Price Lists (Standard Selling, Sale Price List)
- ✅ Shipping Rule (Free shipping over $50)
- ✅ 3 Demo Products with variants (~40 SKUs)
- ✅ Style Attribute Configurators & Variants
- ✅ Configured Commera Settings
- ✅ Published to website with Commera routes

After installation, immediately visit:
- `https://your-site.com/en/products` to see the demo store
- Test the complete purchase workflow

---

### Step 1: Install Required Apps

If not already installed, install the dependencies:

```bash
# Install ERPNext (if not installed)
bench get-app erpnext
bench --site your-site-name install-app erpnext

# Install Webshop
bench get-app webshop
bench --site your-site-name install-app webshop

# Install Payments
bench get-app payments
bench --site your-site-name install-app payments
```

### Step 2: Install Commera

```bash
# Get the Commera app
bench get-app https://github.com/BuildWithHussain/commera

# Install on your site
bench --site your-site-name install-app commera

# Build assets
bench build --app commera
```

### Step 3: Restart Services

```bash
bench restart
```

### Step 4: Verify Installation

After installation, Commera will automatically create:
- ✅ Ecommerce Item Groups (All Item Groups → Ecommerce Website → Men, Women, Kids)
- ✅ Email Templates (Order Confirmation, Order Cancellation, Item In Stock)
- ✅ Payment Mode: Telr

Check that these were created successfully by navigating to:
- **Desk → Stock → Item Group** - You should see "Ecommerce Website" with child groups

---

## Initial Configuration

### Step 1: Configure Commera Settings

Navigate to: **Desk → Commera Ecommerce → Commera Settings**

#### A. Price List Configuration
1. **Default Price List**: Select your main selling price list (e.g., "Standard Selling")
2. **Sale Price List**: Select price list for sale/discounted items (optional)

#### B. Warehouse Configuration
- **Ecommerce Warehouse**: Select the warehouse that will be used for e-commerce orders
  - This should be a warehouse with actual stock available
  - Example: "Stores - Your Company"

#### C. Shipping & Returns
1. **Shipping Rule**: 
   - Navigate to **Desk → Selling → Shipping Rule**
   - Create a new Shipping Rule based on "Net Total"
   - Example: Free shipping above $100, else $10 flat rate
   - Select this rule in Commera Settings

2. **Return Period**: Enter number of days customers can return items (e.g., 14, 30)

3. **Reason for Return**: Add reasons customers can select:
   - Wrong Size
   - Wrong Color
   - Defective Product
   - Changed Mind
   - etc.

4. **Print Format**: Select the print format for invoices (optional)

#### D. Cash on Delivery (COD) Settings
1. **COD Charge**: Enter the fee for COD orders (e.g., 5.00)
2. **COD Charge Applicable Below**: Enter order value below which COD charge applies
3. **Charge Account Head**: Select the income account for COD charges

#### E. Payment Modes
Enable/disable payment methods:
- ☑️ **Telr** - For online card payments (requires Telr Settings configuration)
- ☑️ **Tabby** - For Buy Now Pay Later (requires Tabby app installation)
- ☑️ **COD** - Cash on Delivery

#### F. Email Configuration
1. **Order Confirmation Email Template**: "Order Confirmation"
2. **Order Cancellation Email Template**: "Order Cancellation"
3. **Item In Stock Email Template**: "Item In Stock"
4. **Logo URL**: Enter URL to your company logo for emails
5. **CC Email**: Optional email to CC on all order emails

#### G. Item Group Mapping (Optional)
If you have existing item groups that should map to e-commerce groups:
1. Click on "eCommerce Item Group Mapping" table
2. Add rows mapping:
   - **Original Item Group**: Your existing ERPNext item group
   - **eCommerce Item Group**: Target e-commerce group (Men, Women, Kids, etc.)
3. Click "Sync Item Group Mapping to Existing Items" to apply

**Click Save** after configuring all settings.

---

## Creating Your First Product

There are two ways to create products for the e-commerce website:

### Option 1: Simple Product (Single Variant)

#### Step 1: Create an Item in ERPNext

Navigate to: **Desk → Stock → Item → New**

Fill in the following fields:

**Basic Information:**
- **Item Code**: Unique code (e.g., "TSHIRT-001")
- **Item Name**: Display name (e.g., "Classic Cotton T-Shirt")
- **Item Group**: Select from e-commerce groups (Men, Women, Kids)
- **Default Unit of Measure**: pcs, nos, etc.

**Custom Fields (Commera specific):**
- **DisplayName**: Short display name (e.g., "Cotton Tee")
- **Ecommerce Display Name**: Full e-commerce name (e.g., "Classic Cotton T-Shirt")

**Inventory:**
- ☑️ Maintain Stock
- **Is Stock Item**: Yes
- **Default Warehouse**: Your ecommerce warehouse
- **Opening Stock**: Enter initial quantity (e.g., 100)
- **Valuation Rate**: Cost price

**Sales Details:**
- ☑️ Allow Item to be Sold
- **Default Income Account**: Select appropriate income account

**Website Settings:**
- ☑️ Show in Website (publish to webshop)
- **Route**: Auto-generated or custom (e.g., "classic-cotton-tshirt")
- **Website Image**: Upload product image (recommended: 1000x1000px)
- **Website Warehouse**: Select your e-commerce warehouse
- **Website Item Groups**: Select relevant e-commerce groups

**Item Images:**
- Click "Add Row" in Website Images table
- Upload multiple product images
- First image becomes the main display image

**Description:**
- **Description**: Add detailed product description (supports HTML)
- **Web Long Description**: Extended description for product page

**Pricing:**
After saving the item, create a price:
1. Click "Add Item Price" or go to **Desk → Stock → Item Price → New**
2. **Item Code**: Select your item
3. **Price List**: Select your default selling price list
4. **Rate**: Enter selling price (e.g., 29.99)
5. Save

#### Step 2: Verify Item is Published

1. Save the item
2. Navigate to: **Desk → Website → Website Item**
3. You should see a Website Item created automatically
4. Check that all details are correct

### Option 2: Product with Variants (Using SAC/SAV)

For products with multiple colors/sizes, use the Style Attribute Configurator:

#### Step 1: Create Item Template

Navigate to: **Desk → Stock → Item → New**

**Basic Settings:**
- **Item Code**: Template code (e.g., "TSHIRT-CLASSIC-TEMPLATE")
- **Item Name**: Template name (e.g., "Classic T-Shirt Template")
- ☑️ **Has Variants**: Yes
- **Item Group**: Select e-commerce group

**Attributes Tab:**
Add attributes for variants:
1. Click "Add Row" in Attributes table
2. **Attribute**: Select "Color"
3. Add color values (Red, Blue, Green, etc.)
4. Add another row for **Attribute**: "Size"
5. Add size values (S, M, L, XL, etc.)

**Other Settings:**
- Configure sales details, descriptions, and images as above
- Set default pricing

Save the item template.

#### Step 2: Create Style Attribute Configurator (SAC)

Navigate to: **Desk → Commera Ecommerce → Style Attribute Configurator → New**

1. **Item Template**: Select your template (e.g., "TSHIRT-CLASSIC-TEMPLATE")
2. **Item Attribute**: Select primary attribute (usually "Color")
3. **Recommended Items**: Add items to show as "You May Also Like" (optional)
4. Save

#### Step 3: Create Style Attribute Variants (SAV)

Navigate to: **Desk → Commera Ecommerce → Style Attribute Variant → New**

For each color variant:

1. **Configurator**: Select the SAC you created
2. **Attribute Value**: Select color (e.g., "Red")
3. **Variant Item Code Prefix**: Enter prefix (e.g., "TSHIRT-RED")
4. **Image**: Upload image for this color variant
5. **Description**: Optional description specific to this variant

**Size Configuration:**
Click "Add Row" in the Color Size Items table for each size:
- **Size**: Select size (S, M, L, XL)
- **Item Code Suffix**: Optional suffix (e.g., "-S", "-M")
- **Stock Qty**: Enter available quantity for this size
- **Published on Website**: ☑️ Check to publish
- **Regular Price**: Enter price (will use default if not specified)

Repeat for each color variant.

#### Step 4: Publish Variants

After saving all SAV records:
1. Go back to **Commera Settings**
2. Click "Publish Variants for All Templates"
3. This creates all variant combinations and publishes them to the website

---

## Publishing to Website

### Verify Product Publication

1. Navigate to: **Desk → Website → Website Item**
2. Find your product
3. Check these fields:
   - ☑️ Published
   - Website Item Groups are set
   - Item Group shows correct e-commerce group
   - Images are uploaded
   - Price is set

### Set Item Group Display

Navigate to: **Desk → Stock → Item Group**

For each e-commerce group (Men, Women, Kids):
1. Open the Item Group
2. **Custom Fields:**
   - **DisplayName**: Display name for backend
   - **Ecommerce Display Name**: Display name for website
   - ☑️ **Display on Website**: Check this
3. **Website Settings:**
   - ☑️ **Show in Website**: Check this
   - **Route**: Auto-generated or custom (e.g., "men", "women")
   - **Website Title**: Title for the category page
   - **Description**: Banner/description for category page (supports HTML)
   - **Slideshow**: Optional slideshow for category page
4. Save

---

## Accessing the Frontend

### Default Routes

The Commera frontend uses URL-based language routing:

**English Routes:**
- Homepage: `https://your-site.com/en`
- Product Catalog: `https://your-site.com/en/products`
- Specific Product: `https://your-site.com/en/products/product-slug`
- Cart: `https://your-site.com/en/cart`
- Checkout: `https://your-site.com/en/cart/checkout`
- User Account: `https://your-site.com/en/account/dashboard`

**Arabic Routes (RTL):**
- Homepage: `https://your-site.com/ar`
- Product Catalog: `https://your-site.com/ar/products`
- And so on...

### Testing Your First Product

1. Open browser to: `https://your-site.com/en/products`
2. You should see your published products
3. Click on a product to view details
4. Test add to cart functionality
5. Proceed to checkout to test the full flow

### Guest Checkout vs User Accounts

- **Guest Checkout**: Customers can checkout without creating an account
- **User Accounts**: Customers can register to track orders and save addresses

---

## Advanced Features

### Bulk Operations

#### Bulk Image Upload
For uploading multiple product images at once:
1. Navigate to: **Desk → Commera Ecommerce → Bulk Image Upload**
2. Follow the tool to upload images in bulk

#### Bulk Variant Publishing
To publish multiple variants at once:
1. Navigate to: **Commera Settings → Bulk Actions / Import Tab**
2. Use "Publish Variants for All Templates" button

### Landing Page Configuration

Configure hero banners and featured sections:
1. Navigate to: **Desk → Commera Ecommerce → Landing Page Settings**
2. Add hero banners, featured categories, and promotional sections

### Size Charts

Add size charts for products:
1. Navigate to: **Desk → Commera Ecommerce → Size Chart**
2. Create size charts for different item groups
3. Link to items or item groups

### Payment Gateway Configuration

#### Telr Payment Gateway
1. Navigate to: **Desk → Commera Ecommerce → Telr Settings**
2. Enter:
   - Store ID
   - Auth Key
   - Test/Live Mode settings
3. Save

#### Tabby Buy Now Pay Later
Install the Tabby app and configure:
```bash
bench get-app https://github.com/cinnamonlabs/tabby_frappe
bench --site your-site-name install-app tabby_frappe
```

### Multi-Store Support

Commera supports multiple physical store locations for pickup orders.

---

## Troubleshooting

### Product Not Showing on Website

**Check these in order:**

1. **Item Configuration:**
   - ☑️ Is "Show in Website" checked?
   - Is "Website Warehouse" set?
   - Is stock available in the warehouse?
   - Are images uploaded?

2. **Website Item:**
   - Navigate to Website Item
   - ☑️ Is "Published" checked?
   - Are "Website Item Groups" set?
   - Is the item group correct?

3. **Item Group:**
   - Is the Item Group published to website?
   - ☑️ Is "Show in Website" checked?
   - Are custom display name fields filled?

4. **Price:**
   - Is an Item Price created?
   - Is the Price List correct?
   - Is the price greater than zero?

### Installation Errors

#### "Error creating Ecommerce groups"

This has been fixed in the latest version. If you encounter this:
1. Check that custom fields are installed: `custom_displayname` and `custom_item_group_display_name`
2. Check Error Log in Frappe Desk for detailed error
3. Manually create root Item Group if needed

#### Missing Dependencies

```bash
# Reinstall dependencies
bench --site your-site-name install-app webshop
bench --site your-site-name install-app payments
```

### Frontend Issues

#### Pages Not Loading / 404 Errors

1. **Clear cache:**
```bash
bench --site your-site-name clear-cache
bench --site your-site-name clear-website-cache
```

2. **Rebuild assets:**
```bash
bench build --app commera
```

3. **Restart services:**
```bash
bench restart
```

#### Images Not Displaying

1. Check file permissions on `/public/files/`
2. Verify image paths in Website Item
3. Ensure images are in correct format (JPG, PNG, WebP)
4. Check image file size (recommended < 500KB for optimal performance)

### Checkout Issues

#### Payment Gateway Not Working

1. **Verify payment gateway configuration:**
   - Check Telr Settings are complete
   - Test mode vs Live mode settings
   - API credentials are correct

2. **Check Commera Settings:**
   - Payment modes are enabled
   - COD settings are configured if using COD

#### Orders Not Creating

1. **Check required settings:**
   - Default Price List is set
   - Ecommerce Warehouse is set
   - Company is configured in ERPNext
   - Tax templates are set up (if applicable)

2. **Check user permissions:**
   - Guest user has permissions to create Quotations
   - Sales Order creation permissions are correct

### Performance Optimization

#### Slow Product Pages

1. **Optimize images:**
   - Use WebP format
   - Compress images to < 200KB
   - Use appropriate dimensions (1000x1000px for main images)

2. **Enable caching:**
```bash
# In site_config.json
{
  "enable_website_cache": 1,
  "cache_timeout": 3600
}
```

3. **Database optimization:**
```bash
bench --site your-site-name mariadb
# Run MySQL optimization commands
```

---

## Getting Help

### Resources

- **Documentation**: [ERPNext E-Commerce Docs](https://docs.erpnext.com/docs/user/manual/en/e_commerce)
- **Community Forum**: [Frappe Forum](https://discuss.frappe.io/)
- **GitHub Issues**: [Commera Issues](https://github.com/BuildWithHussain/commera/issues)

### Common Support Channels

1. Create an issue on GitHub with:
   - Frappe/ERPNext versions
   - Detailed error messages
   - Steps to reproduce
   - Screenshots if applicable

2. Post on Frappe Forum with tag `commera`

---

## Next Steps

After completing this setup:

1. **Customize Design**: Modify templates and styling to match your brand
2. **Configure SEO**: Add meta descriptions, keywords for products
3. **Set Up Analytics**: Integrate Google Analytics or similar
4. **Configure Email**: Set up email domain and templates
5. **Test Complete Flow**: Go through entire purchase process
6. **Set Up Shipping**: Configure shipping rules and carriers
7. **Launch**: Announce your store and start selling!

---

## Credits

Commera is developed and maintained by **BWH Studios** - Specializing in Frappe customizations and consulting.

---

**Last Updated**: 2025-10-03
**Version**: 1.0

For the latest updates and detailed documentation, visit the [Commera GitHub Repository](https://github.com/BuildWithHussain/commera).