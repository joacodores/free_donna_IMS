from decimal import Decimal
from django.shortcuts import redirect, get_object_or_404
from django.views.generic import DetailView, View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.contrib import messages

from ..models import Local, Articulo, Transferencia, TransferenciaItem, MovimientoStock
from .utilidades import _get_local_activo


class ArticulosTransferirView(LoginRequiredMixin, View):
    
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
