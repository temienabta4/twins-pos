import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template_string, request, redirect, url_for, flash, send_file

# ReportLab imports for PDF generation
from reportlab.lib.pagesizes import portrait
from reportlab.lib import colors
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "twins_enterprise_secret_key_98765"
DATABASE = "twins_supermarket.db"


# --- DATABASE MANAGEMENT ---

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Sets up database schemas for products, invoices, line items, and employees."""
    with get_db_connection() as conn:
        # 1. Employees Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL DEFAULT 'Cashier',
                is_active INTEGER DEFAULT 1
            )
        """)
        # 2. Products Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                price REAL NOT NULL,
                stock INTEGER NOT NULL DEFAULT 0
            )
        """)
        # 3. Invoices Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL UNIQUE,
                date_time TEXT NOT NULL,
                seller_name TEXT NOT NULL,
                total_amount REAL NOT NULL,
                cash_tendered REAL NOT NULL,
                change_amount REAL NOT NULL
            )
        """)
        # 4. Invoice Line Items Table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS invoice_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                unit_price REAL NOT NULL,
                total_price REAL NOT NULL,
                FOREIGN KEY (invoice_id) REFERENCES invoices (id) ON DELETE CASCADE,
                FOREIGN KEY (product_id) REFERENCES products (id)
            )
        """)

        # Seed default employees if empty
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM employees")
        if cursor.fetchone()[0] == 0:
            default_staff = [
                ("Wkyanos", "Manager"),
                ("Hana", "Cashier"),
                ("Elias", "Cashier")
            ]
            conn.executemany("INSERT INTO employees (name, role) VALUES (?, ?)", default_staff)

        # Seed default products if empty
        cursor.execute("SELECT COUNT(*) FROM products")
        if cursor.fetchone()[0] == 0:
            default_items = [
                ("Double Beef Burger", 6.50, 50),
                ("Fresh Orange Juice", 3.00, 100),
                ("Special Burger Deluxe", 8.50, 30),
                ("Avocado & Mango Juice Mix", 4.00, 60),
                ("Classic French Fries", 2.50, 80)
            ]
            conn.executemany("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)", default_items)

        conn.commit()


# --- AUTO-TEMPLATES SETUP ---
TEMPLATES_DIR = "templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# 1. BASE LAYOUT WITH NAVIGATION
BASE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Twins POS{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
</head>
<body class="bg-slate-50 min-h-screen flex flex-col font-sans">
    <nav class="bg-gradient-to-r from-orange-600 to-amber-500 shadow-md text-white">
        <div class="max-w-7xl mx-auto px-6 py-4 flex flex-col md:flex-row justify-between items-center gap-4">
            <div class="flex items-center space-x-3">
                <i class="fa-solid font-bold text-2xl fa-burger animate-bounce text-yellow-300"></i>
                <span class="text-xl font-extrabold tracking-wide">TWINS JUICE & BURGER</span>
            </div>
            <div class="flex space-x-6 text-sm font-semibold">
                <a href="{{ url_for('billing') }}" class="hover:text-yellow-200 transition"><i class="fa-solid fa-cash-register mr-1"></i> POS Billing</a>
                <a href="{{ url_for('inventory') }}" class="hover:text-yellow-200 transition"><i class="fa-solid fa-boxes-stacked mr-1"></i> Inventory</a>
                <a href="{{ url_for('staff') }}" class="hover:text-yellow-200 transition"><i class="fa-solid fa-users mr-1"></i> Staff Roster</a>
            </div>
        </div>
    </nav>
    <main class="flex-grow max-w-7xl w-full mx-auto p-6">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, msg in messages %}
                    <div class="mb-4 p-4 rounded-lg border shadow-sm {% if category == 'error' %}bg-red-50 border-red-200 text-red-700{% else %}bg-green-50 border-green-200 text-green-700{% endif %} flex justify-between items-center">
                        <span class="font-medium"><i class="fa-solid {% if category == 'error' %}fa-circle-xmark{% else %}fa-circle-check{% endif %} mr-2"></i>{{ msg }}</span>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </main>
    <footer class="bg-slate-800 text-slate-400 py-6 text-center text-sm border-t border-slate-700">
        <div class="mb-2 font-semibold text-slate-300">📍 Addis Abeba, Lafto | 📞 0911255011</div>
        <div class="text-xs">&copy; 2026 Twins Juice & Burger Supermarket. All rights reserved.</div>
    </footer>
</body>
</html>
"""

# 2. POS BILLING PAGE
BILLING_HTML = """
{% extends 'base.html' %}
{% block title %}Twins - POS Terminal{% endblock %}
{% block content %}
<div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
    <!-- Active Order Desk (Columns 1-3) -->
    <div class="lg:col-span-3 bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex flex-col justify-between">
        <div>
            <div class="flex justify-between items-center mb-6">
                <h2 class="text-xl font-bold text-slate-800 flex items-center"><i class="fa-solid fa-cart-shopping text-orange-500 mr-2"></i>Active Checkout Cart</h2>
                {% if cart %}
                <a href="{{ url_for('clear_cart') }}" class="text-xs text-red-500 hover:underline font-semibold"><i class="fa-solid fa-trash-can mr-1"></i>Clear All</a>
                {% endif %}
            </div>

            <!-- Add Item Row -->
            <form action="{{ url_for('add_to_cart') }}" method="POST" class="grid grid-cols-1 sm:grid-cols-3 gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200 mb-6">
                <div class="sm:col-span-2">
                    <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Select Menu Item</label>
                    <select name="product_id" required class="w-full px-3 py-2 border rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm">
                        <option value="" disabled selected>-- Search & Choose Product --</option>
                        {% for p in available_products %}
                            <option value="{{ p.id }}">{{ p.name }} (${{ "%.2f"|format(p.price) }}) - Stock: {{ p.stock }} left</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Qty</label>
                    <div class="flex">
                        <input type="number" name="quantity" min="1" value="1" required class="w-full px-3 py-2 border rounded-l-md focus:outline-none focus:ring-2 focus:ring-orange-500 text-center text-sm font-bold">
                        <button type="submit" class="bg-orange-500 text-white px-4 rounded-r-md hover:bg-orange-600 transition font-bold text-sm">ADD</button>
                    </div>
                </div>
            </form>

            <!-- Checkout Line Items -->
            <div class="overflow-x-auto">
                <table class="w-full text-left text-sm">
                    <thead>
                        <tr class="bg-slate-100 border-b border-slate-200 text-slate-600 font-semibold uppercase text-xs">
                            <th class="py-3 px-4">Menu Item</th>
                            <th class="py-3 px-4 text-center">Quantity</th>
                            <th class="py-3 px-4 text-right">Unit Price</th>
                            <th class="py-3 px-4 text-right">Subtotal</th>
                            <th class="py-3 px-4 text-center">Remove</th>
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100 text-slate-700">
                        {% if cart %}
                            {% for item in cart %}
                            <tr>
                                <td class="py-3.5 px-4 font-bold text-slate-800">{{ item.name }}</td>
                                <td class="py-3.5 px-4 text-center">
                                    <form action="{{ url_for('update_cart_qty', pid=item.id) }}" method="POST" class="inline-block">
                                        <input type="number" name="quantity" min="1" value="{{ item.quantity }}" class="w-16 text-center border rounded py-1 px-2 text-xs font-semibold focus:ring-2 focus:ring-orange-500" onchange="this.form.submit()">
                                    </form>
                                </td>
                                <td class="py-3.5 px-4 text-right">${{ "%.2f"|format(item.price) }}</td>
                                <td class="py-3.5 px-4 text-right font-semibold">${{ "%.2f"|format(item.subtotal) }}</td>
                                <td class="py-3.5 px-4 text-center">
                                    <a href="{{ url_for('remove_from_cart', pid=item.id) }}" class="text-red-500 hover:text-red-700"><i class="fa-solid fa-circle-minus text-base"></i></a>
                                </td>
                            </tr>
                            {% endfor %}
                        {% else %}
                        <tr>
                            <td colspan="5" class="py-16 text-center text-slate-400">
                                <i class="fa-solid fa-basket-shopping text-3xl mb-2 text-slate-300 block"></i>
                                Cart is empty. Select items above to calculate the invoice.
                            </td>
                        </tr>
                        {% endif %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- Order Calculations & Settlement -->
        {% if cart %}
        <div class="border-t border-slate-200 pt-6 mt-6 bg-slate-50 p-6 rounded-xl">
            <form action="{{ url_for('checkout') }}" method="POST" class="space-y-4">
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Select Cashier</label>
                        <select name="seller_name" required class="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500 bg-white text-sm">
                            <option value="" disabled selected>-- Select Staff --</option>
                            {% for seller in sellers %}
                                <option value="{{ seller.name }}">{{ seller.name }} ({{ seller.role }})</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1">Cash Tendered ($)</label>
                        <input type="number" step="0.01" name="cash_tendered" required class="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm" placeholder="0.00">
                    </div>
                    <div class="bg-white p-3 rounded-lg border border-slate-200 flex flex-col justify-center items-end">
                        <span class="text-xs font-bold text-slate-400 uppercase">Grand Total Due</span>
                        <span class="text-2xl font-black text-slate-900">${{ "%.2f"|format(cart_total) }}</span>
                    </div>
                </div>
                <button type="submit" class="w-full bg-green-600 hover:bg-green-700 text-white font-bold py-3.5 px-4 rounded-lg shadow-md transition text-center text-base tracking-wide flex justify-center items-center gap-2">
                    <i class="fa-solid fa-file-invoice-dollar"></i> Process Sale & Calculate Change
                </button>
            </form>
        </div>
        {% endif %}
    </div>

    <!-- Completed Transactions Sidebar (Columns 4-5) -->
    <div class="lg:col-span-2 bg-white p-6 rounded-xl shadow-sm border border-slate-200 flex flex-col justify-between">
        <div>
            <h2 class="text-xl font-bold text-slate-800 mb-6 flex items-center"><i class="fa-solid fa-receipt text-amber-500 mr-2"></i>Receipts Registry</h2>
            <div class="divide-y divide-slate-100 max-h-[550px] overflow-y-auto pr-1">
                {% if invoices %}
                    {% for inv in invoices %}
                    <div class="py-4 flex justify-between items-center text-sm hover:bg-slate-50 rounded-lg p-2 transition">
                        <div>
                            <span class="font-bold text-slate-800 block">{{ inv.invoice_number }}</span>
                            <span class="text-xs text-slate-400 block mb-1">{{ inv.date_time }}</span>
                            <span class="inline-block bg-slate-100 text-slate-600 text-[10px] font-bold px-2 py-0.5 rounded">Cashier: {{ inv.seller_name }}</span>
                        </div>
                        <div class="text-right flex items-center space-x-3">
                            <div>
                                <div class="font-extrabold text-slate-900">${{ "%.2f"|format(inv.total_amount) }}</div>
                                <div class="text-xs text-green-600">Change: ${{ "%.2f"|format(inv.change_amount) }}</div>
                            </div>
                            <a href="{{ url_for('print_pdf', invoice_id=inv.id) }}" class="bg-indigo-600 text-white p-2.5 rounded-lg hover:bg-indigo-700 transition shadow" title="Download PDF Thermal Slip">
                                <i class="fa-solid fa-print"></i>
                            </a>
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="py-16 text-center text-slate-400 text-sm">
                        <i class="fa-solid fa-clock-rotate-left text-2xl mb-2 text-slate-300 block"></i>
                        No sales transactions processed today.
                    </div>
                {% endif %}
            </div>
        </div>
    </div>
</div>
{% endblock %}
"""

# 3. ENTERPRISE INVENTORY PAGE
INVENTORY_HTML = """
{% extends 'base.html' %}
{% block title %}Twins - Inventory Desk{% endblock %}
{% block content %}
<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Left Panel: Create & Edit Catalog Items -->
    <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 h-fit">
        <h2 class="text-lg font-bold text-slate-800 mb-4 flex items-center">
            {% if edit_product %}<i class="fa-solid fa-pen-to-square text-blue-500 mr-2"></i>Edit Menu Details{% else %}<i class="fa-solid fa-circle-plus text-orange-500 mr-2"></i>Register New Menu Item{% endif %}
        </h2>
        <form action="{% if edit_product %}{{ url_for('edit_product', pid=edit_product.id) }}{% else %}{{ url_for('add_product') }}{% endif %}" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Product/Juice Name</label>
                <input type="text" name="name" required value="{{ edit_product.name if edit_product else '' }}" class="w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Standard Sales Price ($)</label>
                <input type="number" step="0.01" name="price" required value="{{ edit_product.price if edit_product else '' }}" class="w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm">
            </div>
            {% if not edit_product %}
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Initial Inventory Balance</label>
                <input type="number" name="stock" required min="0" class="w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm" value="0">
            </div>
            {% endif %}
            <div class="pt-2">
                <button type="submit" class="w-full bg-orange-500 text-white font-bold py-2.5 px-4 rounded-md hover:bg-orange-600 transition text-sm">
                    {% if edit_product %}Save Details{% else %}Add to Menu Catalog{% endif %}
                </button>
                {% if edit_product %}
                    <a href="{{ url_for('inventory') }}" class="block text-center text-slate-500 mt-2 hover:underline text-xs font-semibold">Cancel and Exit</a>
                {% endif %}
            </div>
        </form>
    </div>

    <!-- Right Panel: Inventory Table & Audit Operations -->
    <div class="lg:col-span-2 bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
            <h2 class="text-lg font-bold text-slate-800 flex items-center"><i class="fa-solid fa-boxes-stacked text-amber-500 mr-2"></i>Stock Register & Adjustment Desk</h2>
            <form action="{{ url_for('inventory') }}" method="GET" class="flex max-w-xs w-full">
                <input type="text" name="search" placeholder="Search menu catalog..." value="{{ search_query }}" class="w-full px-3 py-1.5 border border-r-0 rounded-l-md focus:outline-none focus:ring-2 focus:ring-orange-500 text-xs">
                <button type="submit" class="bg-orange-500 text-white px-3 py-1.5 rounded-r-md hover:bg-orange-600 transition text-xs"><i class="fa-solid fa-magnifying-glass"></i></button>
            </form>
        </div>

        <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
                <thead>
                    <tr class="bg-slate-100 border-b border-slate-200 text-slate-600 font-semibold uppercase text-[10px] tracking-wider">
                        <th class="py-3 px-4">Catalog ID</th>
                        <th class="py-3 px-4">Item Name</th>
                        <th class="py-3 px-4">Price</th>
                        <th class="py-3 px-4">Current Stock</th>
                        <th class="py-3 px-4 text-center">Stock Operations (In/Out)</th>
                        <th class="py-3 px-4 text-right">Actions</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 text-slate-700">
                    {% if products %}
                        {% for item in products %}
                        <tr class="hover:bg-slate-50 transition">
                            <td class="py-3 px-4 text-slate-400">#00{{ item.id }}</td>
                            <td class="py-3 px-4 font-bold text-slate-800">{{ item.name }}</td>
                            <td class="py-3 px-4 font-semibold">${{ "%.2f"|format(item.price) }}</td>
                            <td class="py-3 px-4">
                                <span class="px-2 py-0.5 rounded text-[10px] font-bold {% if item.stock <= 10 %}bg-red-100 text-red-600{% else %}bg-green-100 text-green-600{% endif %}">
                                    {{ item.stock }} units
                                </span>
                            </td>
                            <td class="py-3 px-4">
                                <form action="{{ url_for('adjust_stock', pid=item.id) }}" method="POST" class="flex justify-center items-center space-x-1.5">
                                    <input type="number" name="quantity" required min="1" value="1" class="w-12 text-center border rounded py-1 text-xs font-bold focus:ring-1 focus:ring-orange-500">
                                    <button type="submit" name="direction" value="in" class="bg-emerald-500 hover:bg-emerald-600 text-white px-2 py-1 text-[10px] font-bold rounded" title="Restock In">Stock IN</button>
                                    <button type="submit" name="direction" value="out" class="bg-red-500 hover:bg-red-600 text-white px-2 py-1 text-[10px] font-bold rounded" title="Deduct Out">Stock OUT</button>
                                </form>
                            </td>
                            <td class="py-3 px-4 text-right space-x-2">
                                <a href="{{ url_for('inventory', edit=item.id) }}" class="text-blue-500 hover:text-blue-700 text-sm" title="Edit Catalog Entry"><i class="fa-solid fa-pen-to-square"></i></a>
                                <a href="{{ url_for('delete_product', pid=item.id) }}" class="text-red-500 hover:text-red-700 text-sm" onclick="return confirm('Permanently drop this item from the catalog?')" title="Delete"><i class="fa-solid fa-trash-can"></i></a>
                            </td>
                        </tr>
                        {% endfor %}
                    {% else %}
                        <tr>
                            <td colspan="6" class="py-12 text-center text-slate-400">No items registered in catalog.</td>
                        </tr>
                    {% endif %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}
"""

# 4. NEW STAFF ROSTER MANAGEMENT PAGE
STAFF_HTML = """
{% extends 'base.html' %}
{% block title %}Twins - Staff Management{% endblock %}
{% block content %}
<div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
    <!-- Left Column: Add Employees -->
    <div class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 h-fit">
        <h2 class="text-lg font-bold text-slate-800 mb-4 flex items-center"><i class="fa-solid fa-user-plus text-orange-500 mr-2"></i>Register Staff Member</h2>
        <form action="{{ url_for('add_staff') }}" method="POST" class="space-y-4">
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Full Name</label>
                <input type="text" name="name" required placeholder="Employee Name" class="w-full px-4 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500 text-sm">
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">Assigned Role</label>
                <select name="role" required class="w-full px-3 py-2 border rounded-md focus:outline-none focus:ring-2 focus:ring-orange-500 bg-white text-sm">
                    <option value="Cashier">Cashier</option>
                    <option value="Manager">Manager</option>
                    <option value="Supervisor">Supervisor</option>
                    <option value="Sales Agent">Sales Agent</option>
                </select>
            </div>
            <div class="pt-2">
                <button type="submit" class="w-full bg-orange-500 text-white font-bold py-2.5 px-4 rounded-md hover:bg-orange-600 transition text-sm">
                    Add to Roster
                </button>
            </div>
        </form>
    </div>

    <!-- Right Column: Staff Roster Table -->
    <div class="lg:col-span-2 bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <h2 class="text-lg font-bold text-slate-800 mb-6 flex items-center"><i class="fa-solid fa-address-book text-amber-500 mr-2"></i>Active Employee Directory</h2>
        <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
                <thead>
                    <tr class="bg-slate-100 border-b border-slate-200 text-slate-600 font-semibold uppercase text-[10px] tracking-wider">
                        <th class="py-3 px-4">Staff ID</th>
                        <th class="py-3 px-4">Employee Name</th>
                        <th class="py-3 px-4">Assigned Role</th>
                        <th class="py-3 px-4 text-center">POS Terminal Access</th>
                        <th class="py-3 px-4 text-right">Terminate Profile</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 text-slate-700">
                    {% if staff_members %}
                        {% for emp in staff_members %}
                        <tr class="hover:bg-slate-50 transition">
                            <td class="py-3 px-4 text-slate-400">#EMP-00{{ emp.id }}</td>
                            <td class="py-3 px-4 font-bold text-slate-800">{{ emp.name }}</td>
                            <td class="py-3 px-4">
                                <span class="bg-slate-100 text-slate-600 font-bold px-2 py-0.5 rounded text-[10px]">
                                    {{ emp.role }}
                                </span>
                            </td>
                            <td class="py-3 px-4 text-center">
                                <span class="bg-green-100 text-green-700 font-bold px-2 py-0.5 rounded text-[10px]">
                                    Active Cashier
                                </span>
                            </td>
                            <td class="py-3 px-4 text-right">
                                <a href="{{ url_for('delete_staff', emp_id=emp.id) }}" class="text-red-500 hover:text-red-700 text-sm" onclick="return confirm('Remove employee from roster database?')">
                                    <i class="fa-solid fa-trash-can"></i> Remove
                                </a>
                            </td>
                        </tr>
                        {% endfor %}
                    {% else %}
                        <tr>
                            <td colspan="5" class="py-12 text-center text-slate-400">Roster database is empty. Register employees on the left.</td>
                        </tr>
                    {% endif %}
                </tbody>
            </table>
        </div>
    </div>
</div>
{% endblock %}
"""

# Dynamic Template Writer Engine
with open(os.path.join(TEMPLATES_DIR, "base.html"), "w", encoding="utf-8") as f: f.write(BASE_HTML)
with open(os.path.join(TEMPLATES_DIR, "billing.html"), "w", encoding="utf-8") as f: f.write(BILLING_HTML)
with open(os.path.join(TEMPLATES_DIR, "inventory.html"), "w", encoding="utf-8") as f: f.write(INVENTORY_HTML)
with open(os.path.join(TEMPLATES_DIR, "staff.html"), "w", encoding="utf-8") as f: f.write(STAFF_HTML)

# --- APPLICATION SESSION-CART & CONFIGS ---
pos_cart = {}  # In-memory checkout cart format {product_id: quantity}


# --- ROUTE: STAFF REGISTER MANAGEMENT ---
@app.route("/staff")
def staff():
    conn = get_db_connection()
    staff_members = conn.execute("SELECT * FROM employees ORDER BY name ASC").fetchall()
    conn.close()
    return render_template_string(
        open(os.path.join(TEMPLATES_DIR, "staff.html"), encoding="utf-8").read(),
        staff_members=staff_members
    )


@app.route("/staff/add", methods=["POST"])
def add_staff():
    name = request.form.get("name").strip()
    role = request.form.get("role")
    if not name:
        flash("Name cannot be blank.", "error")
        return redirect(url_for("staff"))

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO employees (name, role) VALUES (?, ?)", (name, role))
        conn.commit()
        flash(f"Staff member '{name}' added to roster successfully!", "success")
    except sqlite3.IntegrityError:
        flash(f"An employee named '{name}' is already registered.", "error")
    conn.close()
    return redirect(url_for("staff"))


@app.route("/staff/delete/<int:emp_id>")
def delete_staff(emp_id):
    conn = get_db_connection()
    conn.execute("DELETE FROM employees WHERE id = ?", (emp_id,))
    conn.commit()
    conn.close()
    flash("Employee profile successfully removed from database.", "success")
    return redirect(url_for("staff"))


# --- ROUTE: BILLING (POS VIEW) ---
@app.route("/")
def billing():
    """Point of Sale Active Workspace."""
    conn = get_db_connection()
    available_products = conn.execute("SELECT * FROM products WHERE stock > 0 ORDER BY name ASC").fetchall()
    sellers = conn.execute("SELECT * FROM employees ORDER BY name ASC").fetchall()

    cart_items = []
    cart_total = 0.0
    for pid, qty in pos_cart.items():
        prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        if prod:
            subtotal = prod["price"] * qty
            cart_total += subtotal
            cart_items.append({
                "id": prod["id"],
                "name": prod["name"],
                "price": prod["price"],
                "quantity": qty,
                "subtotal": subtotal
            })

    invoices = conn.execute("SELECT * FROM invoices ORDER BY id DESC").fetchall()
    conn.close()

    return render_template_string(
        open(os.path.join(TEMPLATES_DIR, "billing.html"), encoding="utf-8").read(),
        available_products=available_products,
        cart=cart_items,
        cart_total=cart_total,
        sellers=sellers,
        invoices=invoices
    )


@app.route("/cart/add", methods=["POST"])
def add_to_cart():
    pid = request.form.get("product_id")
    try:
        qty = int(request.form.get("quantity") or 1)
    except ValueError:
        qty = 1

    if not pid:
        flash("Please select a valid menu item.", "error")
        return redirect(url_for("billing"))

    conn = get_db_connection()
    prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()

    if prod:
        current_in_cart = pos_cart.get(int(pid), 0)
        new_qty = current_in_cart + qty
        if new_qty > prod["stock"]:
            flash(f"Insufficient Stock! Only {prod['stock']} units left of '{prod['name']}'.", "error")
        else:
            pos_cart[int(pid)] = new_qty
    return redirect(url_for("billing"))


@app.route("/cart/update/<int:pid>", methods=["POST"])
def update_cart_qty(pid):
    try:
        qty = int(request.form.get("quantity") or 1)
    except ValueError:
        qty = 1

    conn = get_db_connection()
    prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
    conn.close()

    if prod:
        if qty > prod["stock"]:
            flash(f"Insufficient Stock! Only {prod['stock']} available.", "error")
        else:
            pos_cart[pid] = qty
    return redirect(url_for("billing"))


@app.route("/cart/remove/<int:pid>")
def remove_from_cart(pid):
    pos_cart.pop(pid, None)
    return redirect(url_for("billing"))


@app.route("/cart/clear")
def clear_cart():
    pos_cart.clear()
    return redirect(url_for("billing"))


@app.route("/checkout", methods=["POST"])
def checkout():
    if not pos_cart:
        flash("Your active checkout cart is empty.", "error")
        return redirect(url_for("billing"))

    seller_name = request.form.get("seller_name")
    try:
        cash_tendered = float(request.form.get("cash_tendered") or 0.0)
    except ValueError:
        cash_tendered = 0.0

    conn = get_db_connection()
    total_amount = 0.0
    items_to_process = []

    for pid, qty in pos_cart.items():
        prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()
        if not prod:
            continue
        if qty > prod["stock"]:
            flash(f"Inventory issue! '{prod['name']}' stock changed. Transaction halted.", "error")
            conn.close()
            return redirect(url_for("billing"))

        item_total = prod["price"] * qty
        total_amount += item_total
        items_to_process.append({
            "product_id": prod["id"],
            "quantity": qty,
            "unit_price": prod["price"],
            "total_price": item_total,
            "new_stock": prod["stock"] - qty
        })

    if cash_tendered < total_amount:
        flash(f"Insufficient Cash Received! Total is ${total_amount:.2f}.", "error")
        conn.close()
        return redirect(url_for("billing"))

    change_amount = cash_tendered - total_amount
    invoice_num = f"INV-{int(datetime.now().timestamp())}"
    date_str = datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")

    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO invoices (invoice_number, date_time, seller_name, total_amount, cash_tendered, change_amount)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (invoice_num, date_str, seller_name, total_amount, cash_tendered, change_amount))

        invoice_id = cursor.lastrowid

        for item in items_to_process:
            cursor.execute("""
                INSERT INTO invoice_items (invoice_id, product_id, quantity, unit_price, total_price)
                VALUES (?, ?, ?, ?, ?)
            """, (invoice_id, item["product_id"], item["quantity"], item["unit_price"], item["total_price"]))

            # Update inventory table (Stock Out)
            cursor.execute("UPDATE products SET stock = ? WHERE id = ?", (item["new_stock"], item["product_id"]))

        conn.commit()
        pos_cart.clear()
        flash(f"Invoice {invoice_num} finalized successfully!", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Database Error: {e}", "error")
    finally:
        conn.close()

    return redirect(url_for("billing"))


# --- ROUTE: INVENTORY DESK ---
@app.route("/inventory")
def inventory():
    search_query = request.args.get("search", "").strip()
    edit_id = request.args.get("edit", "")

    conn = get_db_connection()
    edit_product = None
    if edit_id:
        edit_product = conn.execute("SELECT * FROM products WHERE id = ?", (edit_id,)).fetchone()

    if search_query:
        products = conn.execute("SELECT * FROM products WHERE name LIKE ? ORDER BY name ASC",
                                (f"%{search_query}%",)).fetchall()
    else:
        products = conn.execute("SELECT * FROM products ORDER BY name ASC").fetchall()
    conn.close()

    return render_template_string(
        open(os.path.join(TEMPLATES_DIR, "inventory.html"), encoding="utf-8").read(),
        products=products,
        edit_product=edit_product,
        search_query=search_query
    )


@app.route("/inventory/add", methods=["POST"])
def add_product():
    name = request.form.get("name").strip()
    try:
        price = float(request.form.get("price") or 0.0)
        stock = int(request.form.get("stock") or 0)
    except ValueError:
        flash("Invalid price or stock inputs.", "error")
        return redirect(url_for("inventory"))

    conn = get_db_connection()
    try:
        conn.execute("INSERT INTO products (name, price, stock) VALUES (?, ?, ?)", (name, price, stock))
        conn.commit()
        flash(f"'{name}' added to product catalog.", "success")
    except sqlite3.IntegrityError:
        flash(f"Product '{name}' already exists in your inventory.", "error")
    conn.close()
    return redirect(url_for("inventory"))


@app.route("/inventory/edit/<int:pid>", methods=["POST"])
def edit_product(pid):
    name = request.form.get("name").strip()
    try:
        price = float(request.form.get("price") or 0.0)
    except ValueError:
        flash("Invalid price input.", "error")
        return redirect(url_for("inventory"))

    conn = get_db_connection()
    try:
        conn.execute("UPDATE products SET name = ?, price = ? WHERE id = ?", (name, price, pid))
        conn.commit()
        flash("Catalog specifications modified.", "success")
    except Exception as e:
        flash(f"Error: {e}", "error")
    conn.close()
    return redirect(url_for("inventory"))


@app.route("/inventory/delete/<int:pid>")
def delete_product(pid):
    conn = get_db_connection()
    conn.execute("DELETE FROM products WHERE id = ?", (pid,))
    conn.commit()
    conn.close()
    flash("Item successfully purged from database catalog.", "success")
    return redirect(url_for("inventory"))


@app.route("/inventory/adjust-stock/<int:pid>", methods=["POST"])
def adjust_stock(pid):
    """Audited dynamic stock management adjustments."""
    direction = request.form.get("direction")  # "in" (restock) or "out" (deduct)
    try:
        qty = int(request.form.get("quantity") or 0)
    except ValueError:
        qty = 0

    if qty <= 0:
        flash("Operation quantity must be greater than zero.", "error")
        return redirect(url_for("inventory"))

    conn = get_db_connection()
    prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid,)).fetchone()

    if prod:
        new_stock = prod["stock"] + qty if direction == "in" else max(0, prod["stock"] - qty)
        conn.execute("UPDATE products SET stock = ? WHERE id = ?", (new_stock, pid))
        conn.commit()
        flash(f"Inventory updated for '{prod['name']}' ({direction.upper()} adjustment of {qty} units).", "success")
    conn.close()
    return redirect(url_for("inventory"))


# --- ROUTE: SLIP REPORT GENERATION (80mm) ---
@app.route("/invoice/print/<int:invoice_id>")
def print_pdf(invoice_id):
    """Draws an 80mm thermal receipt with dynamic phone barcode representation."""
    conn = get_db_connection()
    inv = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
    if not inv:
        conn.close()
        flash("Invoice database record not found.", "error")
        return redirect(url_for("billing"))

    items = conn.execute("""
        SELECT ii.*, p.name FROM invoice_items ii 
        JOIN products p ON ii.product_id = p.id 
        WHERE ii.invoice_id = ?
    """, (invoice_id,)).fetchall()
    conn.close()

    pdf_path = f"twins_invoice_{inv['invoice_number']}.pdf"

    # Standard 80mm thermal roll sizing constraints
    width = 80 * 2.83465
    height = (235 + (len(items) * 18)) * 2.83465

    try:
        c = canvas.Canvas(pdf_path, pagesize=(width, height))
        c.setFillColor(colors.HexColor("#111111"))

        # Receipt Header Title
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(width / 2.0, height - 30, "TWINS JUICE & BURGER")
        c.drawCentredString(width / 2.0, height - 44, "SUPERMARKET")

        # Business Location & Transaction Info
        c.setFont("Helvetica", 7.5)
        c.drawCentredString(width / 2.0, height - 58, "Addis Abeba, Lafto")
        c.drawCentredString(width / 2.0, height - 68, f"Seller: {inv['seller_name']}")
        c.drawCentredString(width / 2.0, height - 78, f"Slip ID: {inv['invoice_number']}")
        c.drawCentredString(width / 2.0, height - 88, inv['date_time'])

        # Header Boundary
        c.setLineWidth(1)
        c.setStrokeColor(colors.HexColor("#333333"))
        c.line(12, height - 96, width - 12, height - 96)

        # Columns
        c.setFont("Courier-Bold", 8.5)
        c.drawString(12, height - 108, "QTY")
        c.drawString(38, height - 108, "ITEM NAME")
        c.drawRightString(width - 12, height - 108, "PRICE")

        c.line(12, height - 113, width - 12, height - 113)

        # Write lines
        y_cursor = height - 126
        c.setFont("Courier", 8.5)

        for item in items:
            c.drawString(12, y_cursor, str(item['quantity']))
            c.drawString(38, y_cursor, item['name'][:18].upper())
            c.drawRightString(width - 12, y_cursor, f"{item['total_price']:.2f}")
            y_cursor -= 15

        # Divider line
        y_cursor -= 2
        c.line(12, y_cursor, width - 12, y_cursor)

        # Totals Block
        y_cursor -= 15
        c.setFont("Courier-Bold", 9)
        c.drawString(12, y_cursor, "TOTAL DUE")
        c.drawRightString(width - 12, y_cursor, f"${inv['total_amount']:.2f}")

        y_cursor -= 15
        c.setFont("Courier", 8.5)
        c.drawString(12, y_cursor, "CASH TENDERED")
        c.drawRightString(width - 12, y_cursor, f"${inv['cash_tendered']:.2f}")

        y_cursor -= 15
        c.drawString(12, y_cursor, "CHANGE DUE")
        c.drawRightString(width - 12, y_cursor, f"${inv['change_amount']:.2f}")

        c.line(12, y_cursor - 6, width - 12, y_cursor - 6)

        # Draw Dynamic Phone Barcode encoding the number: 0911255011
        y_cursor -= 35
        barcode_x_start = (width / 2.0) - 45
        tel_barcode = "0911255011"

        for index, digit in enumerate(tel_barcode):
            # Dynamic stroke thickness mapping to create a functional pattern
            weight_factor = (int(digit) % 2) + 1.2
            c.setLineWidth(weight_factor)
            c.line(barcode_x_start + (index * 9), y_cursor, barcode_x_start + (index * 9), y_cursor - 25)

        # Label telephone value below barcode
        y_cursor -= 34
        c.setFont("Helvetica", 8)
        c.drawCentredString(width / 2.0, y_cursor, "Tel: 0911255011")

        y_cursor -= 12
        c.setFont("Helvetica-BoldOblique", 8.5)
        c.drawCentredString(width / 2.0, y_cursor, "Thank You for Your Visit!")

        c.save()
        return send_file(pdf_path, as_attachment=False)

    except Exception as e:
        flash(f"Report generation error: {e}", "error")
        return redirect(url_for("billing"))


# --- SYSTEM DEPLOYMENT ---
if __name__ == "__main__":
    init_db()
    # On cloud servers, we must run on host "0.0.0.0" and use the system-assigned port
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)