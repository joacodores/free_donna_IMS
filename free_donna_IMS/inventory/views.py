from decimal import Decimal
from email.mime import base
from django.http import Http404
from django.shortcuts import get_object_or_404, render, HttpResponse
from django.urls import reverse_lazy
from django.views.generic import ListView, DetailView, CreateView, UpdateView, View, DeleteView
from django.db.models import Q, Count, Sum, Max, Value
from django.db.models.fields import DecimalField
from django.shortcuts import redirect
from .models import Ingreso, IngresoItem, Local, MovimientoStock, Producto, Articulo, Venta, VentaItem, VentaArticulo
from .forms import CheckoutForm, UserLoginForm, UserRegisterForm, ArticuloCreateForm
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic.edit import FormView
from django.db import transaction
from django.contrib import messages
from datetime import datetime as Datetime, time, timezone, datetime
from django.db.models.functions import TruncDate, Coalesce
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


class ProductoUpdateView(LoginRequiredMixin, UpdateView):
    model = Producto
    fields = ["nombre", "tipo_producto", "material", "marca", "precio"]
    template_name = "inventory/producto/producto_form.html"
    success_url = reverse_lazy("inventory:producto_list")


class ProductoDeleteView(LoginRequiredMixin, View):
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

class ArticuloUpdateView(LoginRequiredMixin, UpdateView):
    model = Articulo
    fields = ["product_id", "sku", "talle", "color"]
    context_object_name = "articulo"
    pk_url_kwarg = "articulo_id"
    template_name = "inventory/articulo/articulo_form.html"
    
    def get_success_url(self):
        return reverse_lazy("inventory:articulo_list")
    
class ArticuloDeleteView(LoginRequiredMixin, DeleteView):
    model = Articulo
    pk_url_kwarg = "articulo_id"
    template_name = "inventory/articulo_confirm_delete.html"
    success_url = reverse_lazy("inventory:articulo_list")
    
class ArticuloListView(LoginRequiredMixin, ListView):
    model = Articulo
    template_name = "inventory/articulo/articulo_list.html"
    context_object_name = "articulos"
    paginate_by = 20
    
    def get_queryset(self):
        qs = super().get_queryset().select_related("product_id")
        estado = (self.request.GET.get("estado") or "DISP").strip().upper()
        local_id= self.request.session.get("local_id")
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
        
        if field not in ["all", "sku", "producto", "color", "talle", "nombre", "marca"]:
            field = "all"
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
            # agrupar por documento: venta_id o ingreso_id (según tipo)
            rows = (base
                    .values("tipo", "venta_id", "ingreso_id")
                    .annotate(
                        fecha=Max("fecha"),
                        items=Count("movimiento_id"),
                        unidades=Sum("cantidad"),
                        costo_total=Coalesce(Sum("costo_unitario"), Value(0, output_field=DecimalField())),
                        venta_total=Coalesce(Sum("precio_unitario"), Value(0, output_field=DecimalField())),
                        profit_total=Coalesce(Sum("profit_unitario"), Value(0, output_field=DecimalField())),
                    )
                    .order_by("-fecha"))
            ctx = {
                "mode": mode,
                "rows": list(rows),
                "tipo": tipo, "q": q, "from": desde, "to": hasta,
            }
            return render(request, self.template_name, ctx)

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

def movimiento_pdf(request):
    # reutilizamos la misma lógica de filtros de MovimientoStockView,
    # pero generando rows (agregados o unitarios) y dibujando líneas.
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
        base = base.filter(barcode__icontains=q) | base.filter(sku__icontains=q) | base.filter(producto__nombre__icontains=q) | base.filter(producto__marca__icontains=q)

    if desde:
        base = base.filter(fecha__date__gte=desde)
    if hasta:
        base = base.filter(fecha__date__lte=hasta)

    # rows según modo (igual que en la view HTML)
    from django.db.models import Sum, Count, Max, Value, DecimalField
    from django.db.models.functions import TruncDate, Coalesce

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
    else:  # doc
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

    y = h - 40
    c.setFont("Helvetica-Bold", 13)
    c.drawString(40, y, f"Movimientos de Stock - Local: {local.nombre}")
    y -= 16
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Modo: {mode} | Tipo: {tipo} | Q: {q} | Desde: {desde or '-'} | Hasta: {hasta or '-'}")
    y -= 18
    c.line(40, y, 560, y)
    y -= 14

    c.setFont("Helvetica", 8)

    def newline():
        nonlocal y
        y -= 12
        if y < 60:
            c.showPage()
            y = h - 40
            c.setFont("Helvetica", 8)

    if mode == "unit":
        c.drawString(40, y, "Fecha")
        c.drawString(120, y, "Tipo")
        c.drawString(160, y, "Art")
        c.drawString(210, y, "Barcode")
        c.drawString(330, y, "Var")
        c.drawRightString(560, y, "Profit")
        newline()

        for m in rows:
            c.drawString(40, y, m.fecha.strftime("%Y-%m-%d %H:%M"))
            c.drawString(120, y, m.tipo)
            c.drawString(160, y, str(m.articulo_id))
            c.drawString(210, y, str(m.barcode))
            c.drawString(330, y, f"{m.talle}/{m.color}")
            c.drawRightString(560, y, f"$ {m.profit_unitario}")
            newline()

    elif mode == "day":
        c.drawString(40, y, "Día")
        c.drawRightString(320, y, "Costo")
        c.drawRightString(440, y, "Venta")
        c.drawRightString(560, y, "Profit")
        newline()

        for r in rows:
            c.drawString(40, y, str(r["dia"]))
            c.drawRightString(320, y, f"$ {r['costo_total']}")
            c.drawRightString(440, y, f"$ {r['venta_total']}")
            c.drawRightString(560, y, f"$ {r['profit_total']}")
            newline()

    elif mode == "variant":
        c.drawString(40, y, "Barcode")
        c.drawString(170, y, "Var")
        c.drawRightString(320, y, "Costo")
        c.drawRightString(440, y, "Venta")
        c.drawRightString(560, y, "Profit")
        newline()

        for r in rows:
            c.drawString(40, y, str(r["barcode"]))
            c.drawString(170, y, f"{r['talle']}/{r['color']}")
            c.drawRightString(320, y, f"$ {r['costo_total']}")
            c.drawRightString(440, y, f"$ {r['venta_total']}")
            c.drawRightString(560, y, f"$ {r['profit_total']}")
            newline()

    else:  # doc
        c.drawString(40, y, "Fecha")
        c.drawString(140, y, "Doc")
        c.drawRightString(320, y, "Costo")
        c.drawRightString(440, y, "Venta")
        c.drawRightString(560, y, "Profit")
        newline()

        for r in rows:
            fecha = r["fecha"].strftime("%Y-%m-%d %H:%M") if r["fecha"] else "-"
            doc = f"V#{r['venta_id']}" if r["tipo"] == "OUT" else f"I#{r['ingreso_id']}"
            c.drawString(40, y, fecha)
            c.drawString(140, y, doc)
            c.drawRightString(320, y, f"$ {r['costo_total']}")
            c.drawRightString(440, y, f"$ {r['venta_total']}")
            c.drawRightString(560, y, f"$ {r['profit_total']}")
            newline()

    c.showPage()
    c.save()
    return response

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
    
class IngresoDetailView(LoginRequiredMixin, DetailView):
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

    y = h - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"VENTA #{venta.venta_id}")
    y -= 16
    c.setFont("Helvetica", 9)
    c.drawString(40, y, f"Fecha: {venta.fecha.strftime('%Y-%m-%d %H:%M')}   Local: {venta.local}   Usuario: {venta.usuario.username}")
    y -= 14
    c.drawString(40, y, f"Método de pago: {venta.get_metodo_de_pago_display()}   Estado: {venta.get_estado_display()}")
    y -= 14
    c.line(40, y, 560, y)
    y -= 16

    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "SKU")
    c.drawString(140, y, "Barcode")
    c.drawString(270, y, "Var")
    c.drawRightString(360, y, "Qty")
    c.drawRightString(430, y, "Precio")
    c.drawRightString(500, y, "Costo")
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
        c.drawRightString(360, y, str(it.cantidad))
        c.drawRightString(430, y, f"$ {it.precio_unitario}")
        c.drawRightString(500, y, f"$ {it.costo_unitario}")
        c.drawRightString(560, y, f"$ {it.total_linea}")
        y -= 12

    y -= 8
    c.line(340, y, 560, y)
    y -= 16
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(560, y, f"Total venta: $ {agg['venta_total'] or 0}")
    y -= 14
    c.drawRightString(560, y, f"Costo total: $ {agg['costo_total'] or 0}")
    y -= 14
    c.drawRightString(560, y, f"Profit: $ {agg['profit_total'] or 0}")

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