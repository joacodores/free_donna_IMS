from decimal import Decimal
from email.mime import base
from django.http import Http404
from django.shortcuts import get_object_or_404, render, HttpResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, DeleteView, TemplateView, FormView
from django.db.models import Q, Count, Sum, Max, Value, CharField, F
from django.db.models.fields import DecimalField
from django.shortcuts import redirect
from sqlalchemy import Cast
from .models import Ingreso, IngresoItem, Local, MovimientoStock, Producto, Articulo, Transferencia, TransferenciaItem, Venta, VentaItem, VentaArticulo
from .forms import CheckoutForm, TransferirArticuloForm, UserLoginForm, UserRegisterForm, ArticuloCreateForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.views.generic.edit import FormView
from django.db import transaction
from django.contrib import messages
from datetime import datetime as Datetime, time, timezone, datetime
from django.db.models.functions import TruncDate, Coalesce, TruncMinute, Concat
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from django.utils import timezone


@login_required
def index(request):
    return render(request, "inventory/index.html")

class SignUpView(View):
    def get(self, request):
        form = UserRegisterForm()
        return render(request, "inventory/auth/signup.html", {"form": form})

    def post(self, request):
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            user = authenticate(username=form.cleaned_data['username'],
                                password=form.cleaned_data['password1'])
            login(request, user)
            return redirect("inventory:producto_list")
        return render(request, "inventory/auth/signup.html", {"form": form})

class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect("inventory:producto_list")
        form = UserLoginForm()
        return render(request, "inventory/auth/login.html", {"form": form})
    
    def post(self, request):
        form = UserLoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request, 
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'])
            if user is not None:
                login(request, user)
                return redirect("inventory:producto_list")
            else:
                form.add_error(None, "Credenciales inválidas")
        return render(request, "inventory/auth/login.html", {"form": form})
    
class LogoutView(View):
    def get(self, request):
        logout(request)
        return redirect("inventory:login")


class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_staff

class ProductoListView(LoginRequiredMixin, ListView):
    model = Producto
    template_name = "inventory/producto/producto_list.html"
    context_object_name = "productos"
    paginate_by = 20  
    
    def get_queryset(self):
        qs = super().get_queryset().order_by("product_id")
        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(nombre__icontains=q)
        return qs
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"] = (self.request.GET.get("q") or "").strip()
        return ctx  

class ProductoDetailView(DetailView):
    model = Producto
    template_name = "inventory/producto_detail.html"
    context_object_name = "producto"
    
class ProductoCreateView(LoginRequiredMixin, CreateView):
    model = Producto
    fields = ["nombre", "tipo_producto", "material", "marca", "precio"]
    template_name = "inventory/producto/producto_form.html"
    success_url = reverse_lazy("inventory:producto_list")


class ProductoUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = Producto
    fields = ["nombre", "tipo_producto", "material", "marca", "precio"]
    template_name = "inventory/producto/producto_form.html"
    success_url = reverse_lazy("inventory:producto_list")


class ProductoDeleteView(LoginRequiredMixin,StaffRequiredMixin, View):
    model = Producto
    template_name = "inventory/producto/producto_confirm_delete.html"
    success_url = reverse_lazy("inventory:producto_list")
    
    def post(self, request, pk):
        producto = Producto.objects.get(pk=pk)
        producto.delete()
        return redirect(self.success_url)


class SetLocalView(LoginRequiredMixin, View):
    def post(self, request):
        local_id = request.POST.get("local_id")
        if Local.objects.filter(local_id=local_id).exists():
            request.session["local_id"] = int(local_id)
        return redirect(request.META.get("HTTP_REFERER", "/"))

class ArticuloUpdateView(LoginRequiredMixin, StaffRequiredMixin, UpdateView):
    model = Articulo
    fields = ["product_id", "sku", "talle", "color"]
    context_object_name = "articulo"
    pk_url_kwarg = "articulo_id"
    template_name = "inventory/articulo/articulo_form.html"
    
    def get_success_url(self):
        return reverse_lazy("inventory:articulo_list")
    
class ArticuloDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Articulo
    pk_url_kwarg = "articulo_id"
    template_name = "inventory/articulo_confirm_delete.html"
    success_url = reverse_lazy("inventory:articulo_list")
    
class ArticuloListView(LoginRequiredMixin, ListView):
    model = Articulo
    template_name = "inventory/articulo/articulo_list.html"
    context_object_name = "articulos"
    paginate_by = 20
    
from django.db.models import Q

class ArticuloListView(LoginRequiredMixin, ListView):
    model = Articulo
    template_name = "inventory/articulo/articulo_list.html"
    context_object_name = "articulos"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset().select_related("product_id")

        estado = (self.request.GET.get("estado") or "DISP").strip().upper()
        local_id = self.request.session.get("local_id")

        if local_id:
            qs = qs.filter(local_id=local_id)

        if estado in ["DISP", "VEND", "BAJA"]:
            qs = qs.filter(estado=estado)

        qs = qs.order_by("created_at", "articulo_id")

        scan = (self.request.GET.get("scan") or "").strip()
        if scan:
            return qs.filter(barcode=scan, estado="DISP")

        q = (self.request.GET.get("q") or "").strip()
        field = (self.request.GET.get("field") or "all").strip().lower()

        allowed = ["all", "sku", "barcode", "producto", "marca", "color", "talle", "id"]
        if field not in allowed:
            field = "all"

        # ✅ No staff: sin búsqueda => no puede explorar
        if (not self.request.user.is_staff) and (not q):
            return qs.none()

        # Si no hay q (staff), devuelve todo (exploración permitida)
        if not q:
            return qs

        if field == "all":
            filt = (
                Q(sku__icontains=q) |
                Q(color__icontains=q) |
                Q(barcode__icontains=q) |
                Q(product_id__nombre__icontains=q) |
                Q(product_id__marca__icontains=q)
            )
            if q.isdigit():
                n = int(q)
                filt |= Q(talle=n) | Q(articulo_id=n)
            return qs.filter(filt)

        if field == "sku":
            return qs.filter(sku__icontains=q)

        if field == "barcode":
            return qs.filter(barcode__icontains=q)

        if field == "producto":
            return qs.filter(product_id__nombre__icontains=q)

        if field == "marca":
            return qs.filter(product_id__marca__icontains=q)

        if field == "color":
            return qs.filter(color__icontains=q)

        if field == "talle":
            return qs.filter(talle=int(q)) if q.isdigit() else qs.none()

        if field == "id":
            return qs.filter(articulo_id=int(q)) if q.isdigit() else qs.none()

        return qs


    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["locales"] = Local.objects.all().order_by("nombre")
        ctx["scan"] = (self.request.GET.get("scan") or "").strip()
        ctx["q"] = (self.request.GET.get("q") or "").strip()

        field = (self.request.GET.get("field") or "all").strip().lower()
        if field not in ["all", "sku", "producto", "marca", "color", "talle", "id", "barcode"]:
            field = "all"
        ctx["field"] = field
        ctx["estado"] = (self.request.GET.get("estado") or "DISP").upper()
        ctx["auto_open_first"] = bool(ctx["scan"] and ctx["articulos"])
        return ctx
    
class ArticuloCreateView(LoginRequiredMixin, FormView):
    template_name = "inventory/articulo/articulo_create.html"
    form_class = ArticuloCreateForm
    success_url = reverse_lazy("inventory:articulo_list")
    
    @transaction.atomic
    def form_valid(self, form):
        producto = form.cleaned_data['product_id']
        sku = form.cleaned_data['sku']
        barcode = form.cleaned_data['barcode']
        talle = form.cleaned_data['talle']
        color = form.cleaned_data['color']
        cantidad = form.cleaned_data['cantidad']
        local = _get_local_activo(self.request)
        referencia = (form.cleaned_data.get('referencia') or "").strip()
        costo_unitario = Decimal(form.cleaned_data.get('costo_unitario', 0))
        
        ingreso = Ingreso.objects.create(
            usuario=self.request.user,
            local=local,
            referencia=referencia,
            nota="Ingreso por carga de artículos"
        )
        total_linea = costo_unitario * cantidad
        item = IngresoItem.objects.create(
            ingreso=ingreso,
            producto=producto,
            sku=sku,
            barcode=barcode,
            talle=talle,
            color=color,
            cantidad=cantidad,
            costo_unitario=costo_unitario,
            total_linea=total_linea
        )
        
        articulos = [
            Articulo(
                product_id=producto,
                sku=sku,
                barcode=barcode,
                estado=Articulo.Estado.DISPONIBLE,
                talle=talle,
                color=color,
                local=local,
                ingreso_item=item
            )
            for _ in range(cantidad)
        ]
        Articulo.objects.bulk_create(articulos)
        creados = list(Articulo.objects
                    .filter(ingreso_item=item, local=local)
                    .order_by("articulo_id")[:cantidad]
        )
        movs = [
            MovimientoStock(
                tipo=MovimientoStock.Tipo.INGRESO,
                local=local,
                usuario=self.request.user,
                articulo=a,
                producto=producto,
                sku=sku,
                barcode=barcode,
                talle=talle,
                color=color,
                cantidad=1,
                costo_unitario=costo_unitario,
                precio_unitario=None,
                profit_unitario=Decimal("0.00"),
                ingreso=ingreso,
                venta=None,
                nota=f"Ingreso #{ingreso.ingreso_id}",
            )
            for a in creados
        ]
        MovimientoStock.objects.bulk_create(movs)
        messages.success(self.request, f"Ingreso #{ingreso.ingreso_id} registrado: {cantidad} unidad(es) de {producto}.")
        return super().form_valid(form)
    

CART_KEY = "pos_cart"

def _get_cart(session):
    return session.get(CART_KEY, {})

def _save_cart(session, cart):
    session[CART_KEY] = cart
    session.modified = True
    
def _cart_totals(cart):
    subtotal = Decimal("0.00")
    for it in cart.values():
        line_total = Decimal(it["precio"]) * int(it["qty"])
        it["line_total"] = str(line_total)  # guardo string para render simple
        subtotal += line_total
    return subtotal, subtotal

def _get_local_activo(request):
    local_id = request.session.get("local_id")
    if not local_id:
        return None
    return Local.objects.get(local_id=local_id)

class POSView(LoginRequiredMixin, View):
    template_name = "inventory/pos/pos.html"
    def get(self, request):
        cart = _get_cart(request.session)
        local=_get_local_activo(request)
        barcodes = [it["barcode"] for it in cart.values()]
        stock_map = {}
        if barcodes and local:
            rows = (Articulo.objects
                    .filter(local=local, barcode__in=barcodes, estado=Articulo.Estado.DISPONIBLE)
                    .values("barcode")
                    .annotate(disponibles=Count("articulo_id"))
                    )
            stock_map = {r["barcode"]: r["disponibles"] for r in rows}
        subtotal, total = _cart_totals(cart)
        hoy = timezone.localdate()  
        ventas_qs = (
            Venta.objects
            .filter(
                usuario=request.user,
                local=local if local else None,
                estado=Venta.Estado.CERRADA,
                fecha__date=hoy,   
            )
            .order_by("-venta_id")
        )
        agg = ventas_qs.aggregate(
            ventas_hoy_count=Count("venta_id"),
            ventas_hoy_total=Coalesce(Sum("total"), Decimal("0.00")),
            ventas_hoy_profit=Coalesce(Sum("profit_total"), Decimal("0.00")),
        )
        ventas_hoy = ventas_qs.values("venta_id", "fecha", "metodo_de_pago", "total", "profit_total")[:50]
        
        return render(request, self.template_name, {
            "cart": cart,
            "stock_map": stock_map,
            "subtotal": subtotal,
            "total": total,
            
            "local_activo": local,
            "hoy": hoy,
            "ventas_hoy": list(ventas_hoy),
            "ventas_hoy_count": agg["ventas_hoy_count"] or 0,
            "ventas_hoy_total": agg["ventas_hoy_total"] or Decimal("0.00"),
            "ventas_hoy_profit": agg["ventas_hoy_profit"] or Decimal("0.00"),
        })    
        
class POSAddItemByBarcodeView(LoginRequiredMixin, View):
    def post(self, request):
        barcode = (request.POST.get("barcode") or "").strip()
        if not barcode:
            messages.error(request, "Escaneá un código de barras.")
            return redirect("inventory:pos")
        local=_get_local_activo(request)
        if not local:
            messages.error(request, "No hay un local activo seleccionado.")
            return redirect("inventory:pos")
        
        art = (Articulo.objects
                .select_related("product_id")
                .filter(local=local,barcode=barcode)
                .order_by("articulo_id")
                .first())
        if not art:
            messages.error(request, f"No existe ningún artículo cargado con código de barras {barcode}.")
            return redirect("inventory:pos")
        
        disponibles = Articulo.objects.filter(local=local, barcode=barcode, estado=Articulo.Estado.DISPONIBLE).count()
        if disponibles <= 0:
            messages.error(request, f"No hay unidades disponibles para el artículo '{art.product_id.nombre}' (Código de barras: {barcode}).")
            return redirect("inventory:pos")
        
        line_key = f"{barcode}|{art.talle}|{art.color}"
        cart = _get_cart(request.session)
        if line_key not in cart:
            precio=getattr(art.product_id, "precio", None)
            if precio is None:
                messages.error(request, f"El producto '{art.product_id.nombre}' no tiene un precio definido.")
                return redirect("inventory:pos")
            cart[line_key] = {
                "producto_id": art.product_id.product_id,
                "producto_nombre": getattr(art.product_id, "nombre", ""),
                "marca": getattr(art.product_id, "marca", ""),
                "sku": art.sku,
                "barcode": art.barcode,
                "talle": art.talle,
                "color": art.color,
                "precio": str(precio),
                "qty": 1,
            }
        else:
            new_qty = int(cart[line_key]["qty"]) + 1
            if new_qty > disponibles:
                messages.error(request, f"No hay stock suficiente. Disponibles: {disponibles}.")
                return redirect("inventory:pos")
            cart[line_key]["qty"] = new_qty
            
        _save_cart(request.session, cart)
        return redirect("inventory:pos")
    
class POSRemoveItemView(LoginRequiredMixin, View):
    def post(self, request):
        key = request.POST.get("key") or ""
        cart = _get_cart(request.session)
        if key in cart:
            del cart[key]
            _save_cart(request.session, cart)
        return redirect("inventory:pos")
    
class POSClearView(LoginRequiredMixin, View):
    def get(self, request):
        _save_cart(request.session, {})
        return redirect("inventory:pos")
    
    def post(self, request):
        _save_cart(request.session, {})
        return redirect("inventory:pos")
    
class POSCheckoutView(LoginRequiredMixin, View):
    template_name = "inventory/pos/pos_checkout.html"

    def get(self, request):
        form = CheckoutForm()
        cart = _get_cart(request.session)
        if not cart:
            messages.info(request, "El carrito está vacío.")
            return redirect("inventory:pos")

        subtotal, total = _cart_totals(cart)

        return render(request, self.template_name, {
            "form": form,
            "cart": cart,
            "total": total,
        })

    @transaction.atomic
    def post(self, request):
        cart = _get_cart(request.session)
        if not cart:
            messages.error(request, "El carrito está vacío.")
            return redirect("inventory:pos")
        local=_get_local_activo(request)
        if not local:
            messages.error(request, "No hay un local activo seleccionado.")
            return redirect("inventory:pos")
        
        form = CheckoutForm(request.POST)
        if not form.is_valid():
            subtotal, total = _cart_totals(cart)
            return render(request, self.template_name, {
                "form": form,
                "cart": cart,
                "total": total,
            })
            
        metodo_de_pago = form.cleaned_data["metodo_pago"]
            
        venta = Venta.objects.create(usuario=request.user, local=local,estado=Venta.Estado.ABIERTA, metodo_de_pago=metodo_de_pago)

        subtotal = Decimal("0.00")
        profit_total = Decimal("0.00")
        
        
        for it in cart.values():
            barcode = it["barcode"]
            qty = int(it["qty"])
            precio = Decimal(it["precio"])

            disponibles_qs = (
                Articulo.objects
                .select_for_update()
                .filter(local=local, barcode=barcode, estado=Articulo.Estado.DISPONIBLE)
                .order_by("articulo_id")
            )
            articulos = list(disponibles_qs[:qty])
            if len(articulos) < qty:
                raise ValueError(
                    f"Stock insuficiente para barcode {barcode}. Pediste {qty}, hay {len(articulos)}."
                )
            
            costo_total = sum(Decimal(a.ingreso_item.costo_unitario) for a in articulos)
            qty_d = Decimal(qty)
            costo_unitario_prom = (costo_total / qty_d) if qty else Decimal("0.00")
            total_linea = precio * qty_d
            profit_linea = (precio - costo_unitario_prom) * qty_d
            
            subtotal += total_linea
            profit_total += profit_linea
            VentaItem.objects.create(
                venta=venta,
                producto_id=it["producto_id"],
                sku=it["sku"],
                barcode=barcode,
                talle=int(it["talle"]),
                color=it["color"],
                cantidad=qty,
                precio_unitario=precio,
                costo_unitario=costo_unitario_prom,
                profit_linea=profit_linea,
                total_linea=total_linea,
            )
            art_ids = [a.articulo_id for a in articulos]
            movs = []
            venta_articulos = []
            for a in articulos:
                costo_u = Decimal(a.ingreso_item.costo_unitario) if a.ingreso_item else Decimal("0.00")
                profit_u = precio - costo_u

                movs.append(MovimientoStock(
                    tipo=MovimientoStock.Tipo.VENTA,
                    local=local,
                    usuario=request.user,
                    articulo=a,
                    producto=a.product_id,
                    barcode=a.barcode,
                    sku=a.sku,
                    talle=a.talle,
                    color=a.color,
                    cantidad=-1,
                    costo_unitario=costo_u,
                    precio_unitario=precio,
                    profit_unitario=profit_u,
                    ingreso=None,
                    venta=venta,
                    nota=f"Venta #{venta.venta_id}",
                ))

                venta_articulos.append(VentaArticulo(venta=venta, articulo=a))
                art_ids.append(a.articulo_id)
            # Marcar unidades como vendidas 
            Articulo.objects.filter(articulo_id__in=[a.articulo_id for a in articulos]).update(
                estado=Articulo.Estado.VENDIDO
            )

            # Registrar unidades vendidas 
            VentaArticulo.objects.bulk_create([
                VentaArticulo(venta=venta, articulo=a) for a in articulos
            ])
            
            MovimientoStock.objects.bulk_create(movs)

        #Cerrar venta 
        venta.subtotal = subtotal
        venta.total = subtotal
        venta.profit_total = profit_total
        venta.estado = Venta.Estado.CERRADA
        venta.save(update_fields=["subtotal", "total", "profit_total", "estado"])

        
        _save_cart(request.session, {})

        messages.success(request, f"Venta #{venta.venta_id} cerrada. Total: $ {venta.total}")
        return redirect("inventory:pos")
    
    
class MovimientoStockView(LoginRequiredMixin, ListView):
    template_name = "inventory/movimientos/movimientos_list.html"
    
    def get(self, request):
        local = _get_local_activo(request)
        if not local:
            return render(request, self.template_name, {
                "error_local": True,
                "mode": "doc",
                "rows": [],
            })
        mode = (request.GET.get("mode") or "doc").strip().lower()
        tipo = (request.GET.get("tipo") or "all").strip().upper()
        q = (request.GET.get("q") or "").strip()
        desde = (request.GET.get("from") or "").strip()
        hasta = (request.GET.get("to") or "").strip()
        base = MovimientoStock.objects.filter(local=local).select_related("local", "usuario", "producto","venta","ingreso", "articulo")
        
        if tipo in ["IN", "OUT", "ADJ", "TRF", "BAJ", "RET"]:
            base = base.filter(tipo=tipo)
        
        if q:
            base = base.filter(
                Q(barcode__icontains=q) |
                Q(sku__icontains=q) |
                Q(producto__nombre__icontains=q) |
                Q(producto__marca__icontains=q)
            )
        if desde:
            d = Datetime.strptime(desde, "%Y-%m-%d").date()
            base = base.filter(fecha__gte=timezone.make_aware(datetime.combine(d, time.min)))

        if hasta:
            h = Datetime.strptime(hasta, "%Y-%m-%d").date()
            base = base.filter(fecha__lt=timezone.make_aware(Datetime.combine(h, time.max)))
        if mode=="unit":
            rows = base.order_by("-fecha", "-movimiento_id")[:500]
            ctx = {
                "mode": mode,
                "rows": rows,   
                "tipo": tipo,
                "q": q,
                "from": desde,
                "to": hasta,
            }
            return render(request, self.template_name, ctx)
        if mode == "doc":
            rows = (base
                    .values("tipo", "venta_id", "ingreso_id", "transferencia_id")
                    .annotate(
                        fecha=Max("fecha"),
                        items=Count("movimiento_id"),
                        unidades=Sum("cantidad"),
                        costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                        venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                        profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                    )
                    .order_by("-fecha"))

            return render(request, self.template_name, {
                "mode": mode,
                "rows": list(rows),
                "tipo": tipo, "q": q, "from": desde, "to": hasta,
            })

        if mode == "day":
                rows = (base
                        .annotate(dia=TruncDate("fecha"))
                        .values("dia")
                        .annotate(
                            movimientos=Count("movimiento_id"),
                            unidades=Sum("cantidad"),
                            costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                            venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                            profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                        )
                        .order_by("-dia"))
                ctx = {
                    "mode": mode,
                    "rows": list(rows),
                    "tipo": tipo, "q": q, "from": desde, "to": hasta,
                }
                return render(request, self.template_name, ctx)
        if mode == "variant":
            rows = (base
                    .values("barcode", "sku", "talle", "color", "producto_id", "producto__nombre", "producto__marca")
                    .annotate(
                        movimientos=Count("movimiento_id"),
                        unidades=Sum("cantidad"),
                        costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                        venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                        profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                        last_fecha=Max("fecha"),
                    )
                    .order_by("barcode", "talle", "color"))
            ctx = {
                "mode": mode,
                "rows": list(rows),
                "tipo": tipo, "q": q, "from": desde, "to": hasta,
            }
            return render(request, self.template_name, ctx)

        # fallback
        return render(request, self.template_name, {"mode": "doc", "rows": []})

def money(x):
    if x is None:
        x = Decimal("0.00")
    # formato simple, podés mejorar con locale si querés
    return f"$ {Decimal(x):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def safe(s, maxlen=80):
    s = "" if s is None else str(s)
    return s[:maxlen]

def draw_brand_header(c, w, h, title, subtitle_lines):
    # header “profesional” (sobrio)
    top = h - 36
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, top, title)

    y = top - 16
    c.setFont("Helvetica", 9)
    for line in subtitle_lines:
        c.drawString(40, y, line)
        y -= 12

    # separador
    c.setLineWidth(0.8)
    c.line(40, y, w - 40, y)
    return y - 14  # y inicial de contenido

def ensure_space(c, w, h, y, min_y=70, repeat_header_fn=None):
    """
    Si no hay espacio, nueva página y reimprime header si te pasan repeat_header_fn.
    repeat_header_fn debe devolver un y nuevo.
    """
    if y < min_y:
        c.showPage()
        if repeat_header_fn:
            return repeat_header_fn()
        return h - 60
    return y

def draw_table_header(c, y, cols):
    """
    cols: lista de tuplas (x, text, align) align: 'L' o 'R'
    """
    c.setFont("Helvetica-Bold", 9)
    for x, text, align in cols:
        if align == "R":
            c.drawRightString(x, y, text)
        else:
            c.drawString(x, y, text)
    c.setFont("Helvetica", 9)
    return y - 12


def movimiento_pdf(request):
    local = _get_local_activo(request)
    if not local:
        return HttpResponse("No hay local activo.", status=400)

    mode = (request.GET.get("mode") or "doc").strip().lower()
    tipo = (request.GET.get("tipo") or "all").strip().upper()
    q = (request.GET.get("q") or "").strip()
    desde = (request.GET.get("from") or "").strip()
    hasta = (request.GET.get("to") or "").strip()

    base = (MovimientoStock.objects
            .filter(local=local)
            .select_related("producto", "venta", "ingreso", "articulo", "usuario"))

    if tipo in ["IN", "OUT", "ADJ", "TRF", "BAJ", "RET"]:
        base = base.filter(tipo=tipo)

    if q:
        base = (base.filter(barcode__icontains=q) |
                base.filter(sku__icontains=q) |
                base.filter(producto__nombre__icontains=q) |
                base.filter(producto__marca__icontains=q))

    if desde:
        base = base.filter(fecha__date__gte=desde)
    if hasta:
        base = base.filter(fecha__date__lte=hasta)

    # ---- NUEVO: si es un reporte SOLO DE VENTAS, lo renderizamos “bonito”
    is_sales_report = (mode == "doc" and tipo in ["OUT", "VENTA"])  # ajustá si tu tipo real de venta es "OUT"
    # Si tu enum real en MovimientoStock para ventas es MovimientoStock.Tipo.VENTA,
    # entonces setearías is_sales_report si tipo == "OUT" (como venís usando en UI)
    # y el filtro del base ya te deja solo ventas.

    if is_sales_report:
        return _ventas_report_pdf(request, local, base, desde, hasta, q, tipo)

    # ---- lo que ya tenías para unit/day/variant/doc (igual que tu versión actual)
    if mode == "unit":
        rows = list(base.order_by("-fecha", "-movimiento_id")[:1500])
    elif mode == "day":
        rows = list(base.annotate(dia=TruncDate("fecha")).values("dia").annotate(
            movimientos=Count("movimiento_id"),
            unidades=Sum("cantidad"),
            costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
            venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
            profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
        ).order_by("-dia"))
    elif mode == "variant":
        rows = list(base.values("barcode","sku","talle","color","producto__nombre","producto__marca").annotate(
            movimientos=Count("movimiento_id"),
            unidades=Sum("cantidad"),
            costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
            venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
            profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
            last_fecha=Max("fecha"),
        ).order_by("barcode","talle","color"))
    else:
        rows = list(base.values("tipo","venta_id","ingreso_id").annotate(
            fecha=Max("fecha"),
            items=Count("movimiento_id"),
            costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
            venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
            profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
        ).order_by("-fecha"))

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="movimientos.pdf"'
    c = canvas.Canvas(response, pagesize=A4)
    w, h = A4

    y = draw_brand_header(
        c, w, h,
        title=f"Movimientos de Stock - {local.nombre}",
        subtitle_lines=[
            f"Modo: {mode}  |  Tipo: {tipo}  |  Búsqueda: {q or '-'}",
            f"Rango: {desde or '-'} a {hasta or '-'}  |  Generado: {timezone.localtime().strftime('%Y-%m-%d %H:%M')}",
        ]
    )

    # ... tu render actual de rows (unit/day/variant/doc) ...
    # (copiá y pegá tal cual tu lógica existente de imprimir filas)
    # (no la repito acá para no hacer ruido)

    c.showPage()
    c.save()
    return response


def _ventas_report_pdf(request, local, base_qs, desde, hasta, q, tipo):
    """
    Reporte de ventas: agrupa por venta, imprime items, NO muestra costo por artículo,
    muestra costo total por venta y profit total al final.
    """
    from django.db.models import Q

    # ventas involucradas desde los movimientos
    venta_ids = list(
        base_qs.exclude(venta_id=None)
               .values_list("venta_id", flat=True)
               .distinct()
    )

    ventas = (Venta.objects
              .select_related("usuario", "local")
              .prefetch_related("items")   # tu related_name
              .filter(venta_id__in=venta_ids, local=local)
              .order_by("-fecha"))

    # Totales globales desde MovimientoStock (fuente de verdad de costo/venta/profit)
    global_agg = (base_qs
                  .filter(venta_id__in=venta_ids)
                  .aggregate(
                      ventas=Count("venta_id", distinct=True),
                      unidades=Count("movimiento_id"),
                      costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                      venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                      profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                  ))

    usuarios = sorted({v.usuario.get_full_name().strip() or v.usuario.username for v in ventas})
    usuarios_txt = ", ".join(usuarios) if usuarios else "-"

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = 'inline; filename="reporte_ventas.pdf"'
    c = canvas.Canvas(resp, pagesize=A4)
    w, h = A4

    def header():
        return draw_brand_header(
            c, w, h,
            title=f"Reporte de Ventas - {local.nombre}",
            subtitle_lines=[
                f"Rango: {desde or '-'} a {hasta or '-'}  |  Búsqueda: {q or '-'}",
                f"Usuarios: {usuarios_txt}",
                f"Generado: {timezone.localtime().strftime('%Y-%m-%d %H:%M')}",
            ]
        )

    y = header()

    # “summary box”
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Resumen")
    y -= 12
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Comprobantes: {global_agg['ventas'] or 0}   Unidades: {global_agg['unidades'] or 0}")
    y -= 12
    c.drawString(40, y, f"Vendido: {money(global_agg['venta_total'])}   Costo: {money(global_agg['costo_total'])}   Resultado: {money(global_agg['profit_total'])}")
    y -= 16


    # columnas de items (sin costo por artículo)
    item_cols = [
        (40,  "SKU", "L"),
        (120, "Barcode", "L"),
        (205, "Producto", "L"),
        (380, "Var", "L"),
        (455, "Qty", "R"),
        (520, "Precio", "R"),
        (w - 40, "Importe", "R"),
    ]

    for v in ventas:
        # agregados por venta desde MovimientoStock
        vagg = (MovimientoStock.objects
                .filter(venta=v, tipo=MovimientoStock.Tipo.VENTA)  # ajustá si corresponde
                .aggregate(
                    unidades=Count("movimiento_id"),
                    costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                    venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                    profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                ))
        
        if hasattr(v.usuario, "get_full_name"):
            user_label = v.usuario.get_full_name().strip()
        else:
            user_label = ""
    
        if not user_label:
            user_label = v.usuario.username
    
        y = ensure_space(c, w, h, y, min_y=110, repeat_header_fn=header)
        # header de venta
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, f"Comprobante {v.venta_id}")
        c.setFont("Helvetica", 9)
        c.drawRightString(w - 40, y, v.fecha.strftime("%Y-%m-%d %H:%M"))
        y -= 12
        c.drawString(40, y, f"Usuario: {user_label}   Pago: {v.get_metodo_de_pago_display()}")
        y -= 10
        c.line(40, y, w - 40, y)
        y -= 12

        # table header
        y = draw_table_header(c, y, item_cols)

        items = list(v.items.all().order_by("item_id"))
        for it in items:
            y = ensure_space(c, w, h, y, min_y=80, repeat_header_fn=header)

            # campos: adaptá a tu modelo VentaItem real
            sku = safe(getattr(it, "sku", ""), 14)
            barcode = safe(getattr(it, "barcode", ""), 16)
            # producto: si tu item tiene nombre/marca, usá eso; si no, armalo desde it.producto
            producto_txt = safe(getattr(it, "producto_nombre", None) or getattr(it, "nombre", None) or getattr(getattr(it, "producto", None), "nombre", "") , 32)
            marca_txt = getattr(it, "marca", None) or getattr(getattr(it, "producto", None), "marca", "")
            if marca_txt:
                producto_txt = safe(f"{producto_txt} ({marca_txt})", 40)

            talle = getattr(it, "talle", "")
            color = getattr(it, "color", "")
            var_txt = safe(f"{talle}/{color}", 10)

            qty = int(getattr(it, "cantidad", 1) or 1)
            precio_u = Decimal(getattr(it, "precio_unitario", 0) or 0)
            total_linea = precio_u * qty  # NO usamos costo por ítem

            c.setFont("Helvetica", 9)
            c.drawString(40, y, sku)
            c.drawString(120, y, barcode)
            c.drawString(205, y, producto_txt)
            c.drawString(380, y, var_txt)
            c.drawRightString(455, y, str(qty))
            c.drawRightString(520, y, money(precio_u))
            c.drawRightString(w - 40, y, money(total_linea))
            y -= 12

        # subtotal venta
        y -= 6
        y = ensure_space(c, w, h, y, min_y=80, repeat_header_fn=header)
        c.setLineWidth(0.6)
        c.line(320, y, w - 40, y)
        y -= 14
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(w - 40, y,
            f"Total: {money(vagg['venta_total'])}   Costo: {money(vagg['costo_total'])}   Resultado: {money(vagg['profit_total'])}"
        )
        y -= 16

    # footer global
    y = ensure_space(c, w, h, y, min_y=90, repeat_header_fn=header)
    c.setLineWidth(1.0)
    c.line(40, y, w - 40, y)
    y -= 18
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, y, "Totales del reporte")
    y -= 14
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(w - 40, y, f"Total vendido: {money(global_agg['venta_total'])}")
    y -= 14
    c.drawRightString(w - 40, y, f"Costo total: {money(global_agg['costo_total'])}")
    y -= 14
    c.drawRightString(w - 40, y, f"PROFIT TOTAL: {money(global_agg['profit_total'])}")

    c.showPage()
    c.save()
    return resp

class VentaDetailView(LoginRequiredMixin, DetailView):
    model = Venta
    template_name = "inventory/movimientos/venta_detail.html"
    context_object_name = "venta"
    pk_url_kwarg = "venta_id"
    
    def get_object(self, queryset=None):
        local = _get_local_activo(self.request)
        qs = Venta.objects.select_related("usuario", "local")
        obj = get_object_or_404(qs, venta_id=self.kwargs["venta_id"])
        if local and obj.local_id != local.local_id:
            raise get_object_or_404(Venta, venta_id=-1)
        return obj
    
    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        venta = ctx["venta"]
        
        items = list(venta.items.all().order_by("item_id"))
        ctx["items"] = items
        
        unidades = (MovimientoStock.objects
                    .select_related("articulo")
                    .filter(venta=venta, tipo=MovimientoStock.Tipo.VENTA)
                    .order_by("movimiento_id"))
        ctx["unidades"] = unidades
        
        agg = (MovimientoStock.objects
               .filter(venta=venta, tipo=MovimientoStock.Tipo.VENTA)
               .aggregate(
                   unidades=Count("movimiento_id"),
                   costo_total=Sum("costo_unitario"),
                   venta_total=Sum("precio_unitario"),
                   profit_total=Sum("profit_unitario"),
               ))
        ctx["ms_totals"] = {
            "unidades": agg["unidades"] or 0,
            "costo_total": agg["costo_total"] or Decimal("0.00"),
            "venta_total": agg["venta_total"] or Decimal("0.00"),
            "profit_total": agg["profit_total"] or Decimal("0.00"),
        }
        return ctx
    
class IngresoDetailView(LoginRequiredMixin, StaffRequiredMixin, DetailView):
    model = Ingreso
    template_name = "inventory/movimientos/ingreso_detail.html"
    context_object_name = "ingreso"
    pk_url_kwarg = "ingreso_id"

    def get_object(self, queryset=None):
        local = _get_local_activo(self.request)
        qs = Ingreso.objects.select_related("usuario", "local")
        obj = get_object_or_404(qs, ingreso_id=self.kwargs["ingreso_id"])
        if local and obj.local_id != local.local_id:
            raise get_object_or_404(Ingreso, ingreso_id=-1)
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ingreso = ctx["ingreso"]

        items = list(ingreso.items.all().order_by("item_id"))
        ctx["items"] = items

        unidades = (MovimientoStock.objects
                    .select_related("articulo")
                    .filter(ingreso=ingreso, tipo=MovimientoStock.Tipo.INGRESO)
                    .order_by("movimiento_id"))
        ctx["unidades"] = unidades

        agg = (MovimientoStock.objects
               .filter(ingreso=ingreso, tipo=MovimientoStock.Tipo.INGRESO)
               .aggregate(
                   unidades=Count("movimiento_id"),
                   costo_total=Sum("costo_unitario"),
               ))
        ctx["ms_totals"] = {
            "unidades": agg["unidades"] or 0,
            "costo_total": agg["costo_total"] or Decimal("0.00"),
        }
        return ctx
    
def venta_pdf(request, venta_id: int):
    local = _get_local_activo(request)
    venta = get_object_or_404(Venta.objects.select_related("local","usuario"), venta_id=venta_id)
    if local and venta.local_id != local.local_id:
        return HttpResponse("No autorizado para este local.", status=403)

    items = list(venta.items.all().order_by("item_id"))

    agg = (MovimientoStock.objects
           .filter(venta=venta, tipo=MovimientoStock.Tipo.VENTA)
           .aggregate(
               unidades=Count("movimiento_id"),
               costo_total=Sum("costo_unitario"),
               venta_total=Sum("precio_unitario"),
               profit_total=Sum("profit_unitario"),
           ))

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="venta_{venta_id}.pdf"'
    c = canvas.Canvas(resp, pagesize=A4)
    w, h = A4

    def header():
        return draw_brand_header(
            c, w, h,
            title=f"Comprobante / Detalle de Venta #{venta.venta_id}",
            subtitle_lines=[
                f"Fecha: {venta.fecha.strftime('%Y-%m-%d %H:%M')}  |  Local: {venta.local}  |  Usuario: {venta.usuario.username}",
                f"Método de pago: {venta.get_metodo_de_pago_display()}  |  Estado: {venta.get_estado_display()}",
                f"Generado: {timezone.localtime().strftime('%Y-%m-%d %H:%M')}",
            ]
        )

    y = header()

    cols = [
        (40, "SKU", "L"),
        (120, "Barcode", "L"),
        (210, "Var", "L"),
        (300, "Descripción", "L"),
        (450, "Qty", "R"),
        (520, "Precio", "R"),
        (w - 40, "Importe", "R"),
    ]

    y = draw_table_header(c, y, cols)

    for it in items:
        y = ensure_space(c, w, h, y, min_y=80, repeat_header_fn=header)

        sku = safe(getattr(it, "sku", ""), 14)
        barcode = safe(getattr(it, "barcode", ""), 16)
        var_txt = safe(f"{getattr(it,'talle','')}/{getattr(it,'color','')}", 10)

        qty = int(getattr(it, "cantidad", 1) or 1)
        precio_u = Decimal(getattr(it, "precio_unitario", 0) or 0)
        total_linea = precio_u * qty

        # descripción más “humana”
        desc = safe(getattr(it, "nombre", None) or getattr(getattr(it, "producto", None), "nombre", ""), 40)
        marca = getattr(it, "marca", None) or getattr(getattr(it, "producto", None), "marca", "")
        if marca:
            desc = safe(f"{desc} ({marca})", 46)

        c.drawString(40, y, sku)
        c.drawString(120, y, barcode)
        c.drawString(210, y, var_txt)
        c.drawString(300, y, desc)
        c.drawRightString(450, y, str(qty))
        c.drawRightString(520, y, money(precio_u))
        c.drawRightString(w - 40, y, money(total_linea))
        y -= 12

    # Totales
    y -= 6
    y = ensure_space(c, w, h, y, min_y=90, repeat_header_fn=header)
    c.line(320, y, w - 40, y)
    y -= 16
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(w - 40, y, f"Total vendido: {money(agg['venta_total'] or 0)}")
    y -= 14
    c.drawRightString(w - 40, y, f"Costo total (sin detalle): {money(agg['costo_total'] or 0)}")
    y -= 14
    c.drawRightString(w - 40, y, f"Profit: {money(agg['profit_total'] or 0)}")

    c.showPage()
    c.save()
    return resp


def ingreso_pdf(request, ingreso_id: int):
    local = _get_local_activo(request)
    ingreso = get_object_or_404(Ingreso.objects.select_related("local","usuario"), ingreso_id=ingreso_id)
    if local and ingreso.local_id != local.local_id:
        return HttpResponse("No autorizado para este local.", status=403)

    items = list(ingreso.items.all().order_by("item_id"))
    agg = (MovimientoStock.objects
           .filter(ingreso=ingreso, tipo=MovimientoStock.Tipo.INGRESO)
           .aggregate(
               unidades=Count("movimiento_id"),
               costo_total=Sum("costo_unitario"),
           ))

    resp = HttpResponse(content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="ingreso_{ingreso_id}.pdf"'
    c = canvas.Canvas(resp, pagesize=A4)
    w, h = A4

    y = h - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"INGRESO #{ingreso.ingreso_id}")
    y -= 16
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Fecha: {ingreso.fecha.strftime('%Y-%m-%d %H:%M')}   Local: {ingreso.local}   Usuario: {ingreso.usuario.username}")
    y -= 14
    if ingreso.referencia:
        c.drawString(40, y, f"Referencia: {ingreso.referencia}")
        y -= 14
    if ingreso.nota:
        c.drawString(40, y, f"Nota: {ingreso.nota[:90]}")
        y -= 14

    c.line(40, y, 560, y)
    y -= 16

    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "SKU")
    c.drawString(140, y, "Barcode")
    c.drawString(270, y, "Var")
    c.drawRightString(380, y, "Qty")
    c.drawRightString(470, y, "Costo u.")
    c.drawRightString(560, y, "Total")
    y -= 12
    c.setFont("Helvetica", 9)

    for it in items:
        if y < 80:
            c.showPage()
            y = h - 40
            c.setFont("Helvetica", 9)

        c.drawString(40, y, str(it.sku)[:18])
        c.drawString(140, y, str(it.barcode)[:18])
        c.drawString(270, y, f"{it.talle}/{it.color}"[:10])
        c.drawRightString(380, y, str(it.cantidad))
        c.drawRightString(470, y, f"$ {it.costo_unitario}")
        c.drawRightString(560, y, f"$ {it.total_linea}")
        y -= 12

    y -= 8
    c.line(360, y, 560, y)
    y -= 16
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(560, y, f"Costo total: $ {agg['costo_total'] or 0}")
    y -= 14
    c.setFont("Helvetica", 9)
    c.drawRightString(560, y, f"Unidades: {agg['unidades'] or 0}")

    c.showPage()
    c.save()
    return resp



class ArticulosTransferirView(LoginRequiredMixin, StaffRequiredMixin, View):
    
    @transaction.atomic
    def post(self, request):
        local_origen = _get_local_activo(request)
        if not local_origen:
            messages.error(request, "No hay un local activo seleccionado.")
            return redirect("inventory:articulo_list")

        destino_id = (request.POST.get("destino_id") or "").strip()
        barcode = (request.POST.get("barcode") or "").strip()
        nota_user = (request.POST.get("nota") or "").strip()
        qty_raw = (request.POST.get("qty") or "1").strip()

        if not destino_id or not barcode:
            messages.error(request, "Faltan datos para transferir (destino/barcode).")
            return redirect("inventory:articulo_list")

        try:
            qty = int(qty_raw)
        except ValueError:
            qty = 0

        if qty <= 0:
            messages.error(request, "La cantidad debe ser mayor a 0.")
            return redirect("inventory:articulo_list")

        destino = get_object_or_404(Local, local_id=destino_id)
        if destino.local_id == local_origen.local_id:
            messages.error(request, "El destino debe ser distinto al local origen.")
            return redirect("inventory:articulo_list")

        # Seleccionamos N artículos DISPONIBLES de ese barcode en el local origen
        qs = (Articulo.objects
              .select_for_update()
              .select_related("product_id")
              .filter(local=local_origen, barcode=barcode, estado=Articulo.Estado.DISPONIBLE)
              .order_by("articulo_id"))

        articulos = list(qs[:qty])
        if len(articulos) < qty:
            messages.error(request, f"Stock insuficiente. Pediste {qty} y hay {len(articulos)} disponibles.")
            return redirect("inventory:articulo_list")

        # Documento transferencia
        trf = Transferencia.objects.create(
            local_origen=local_origen,
            local_destino=destino,
            usuario=request.user,
            nota=nota_user,
        )

        # Items
        TransferenciaItem.objects.bulk_create([
            TransferenciaItem(
                transferencia=trf,
                articulo=a,
                sku=a.sku,
                barcode=a.barcode,
                talle=a.talle,
                color=a.color,
            ) for a in articulos
        ])

        # Mover artículos al destino (en batch)
        art_ids = [a.articulo_id for a in articulos]
        Articulo.objects.filter(articulo_id__in=art_ids).update(local=destino)

        # Movimientos: salida (origen) y entrada (destino)
        movs = []
        for a in articulos:
            nota = f"Transferencia #{trf.transferencia_id}: {local_origen.nombre} → {destino.nombre}. {nota_user}".strip()

            # salida
            movs.append(MovimientoStock(
                tipo=MovimientoStock.Tipo.TRANSFERENCIA,
                local=local_origen,
                local_origen=local_origen,
                local_destino=destino,
                transferencia=trf,
                usuario=request.user,
                articulo=a,
                producto=a.product_id,
                sku=a.sku,
                barcode=a.barcode,
                talle=a.talle,
                color=a.color,
                cantidad=-1,
                costo_unitario=Decimal("0.00"),
                precio_unitario=None,
                profit_unitario=Decimal("0.00"),
                ingreso=None,
                venta=None,
                nota=nota,
            ))
            # entrada
            movs.append(MovimientoStock(
                tipo=MovimientoStock.Tipo.TRANSFERENCIA,
                local=destino,
                local_origen=local_origen,
                local_destino=destino,
                transferencia=trf,
                usuario=request.user,
                articulo=a,
                producto=a.product_id,
                sku=a.sku,
                barcode=a.barcode,
                talle=a.talle,
                color=a.color,
                cantidad=+1,
                costo_unitario=Decimal("0.00"),
                precio_unitario=None,
                profit_unitario=Decimal("0.00"),
                ingreso=None,
                venta=None,
                nota=nota,
            ))

        MovimientoStock.objects.bulk_create(movs)

        messages.success(request, f"Transferencia #{trf.transferencia_id} realizada: {qty} unidad(es).")
        return redirect("inventory:transferencia_detail", transferencia_id=trf.transferencia_id)

class TransferenciaDetailView(LoginRequiredMixin, DetailView):
    model = Transferencia
    template_name = "inventory/movimientos/transferencia_detail.html"
    context_object_name = "trf"
    pk_url_kwarg = "transferencia_id"

    def get_object(self, queryset=None):
        local = _get_local_activo(self.request)
        qs = Transferencia.objects.select_related("local_origen", "local_destino", "usuario")
        obj = get_object_or_404(qs, transferencia_id=self.kwargs["transferencia_id"])
        # Solo ver si el local activo participa
        if local and (obj.local_origen_id != local.local_id and obj.local_destino_id != local.local_id):
            raise get_object_or_404(Transferencia, transferencia_id=-1)
        return obj

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        trf = ctx["trf"]
        ctx["items"] = list(trf.items.select_related("articulo").order_by("item_id"))
        return ctx
