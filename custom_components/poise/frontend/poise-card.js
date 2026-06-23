/* poise-card 0.51.0 — bundled, served by the Poise integration (ADR-0040) */
var B=globalThis,D=B.ShadowRoot&&(B.ShadyCSS===void 0||B.ShadyCSS.nativeShadow)&&"adoptedStyleSheets"in Document.prototype&&"replace"in CSSStyleSheet.prototype,q=Symbol(),at=new WeakMap,k=class{constructor(t,e,s){if(this._$cssResult$=!0,s!==q)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=t,this.t=e}get styleSheet(){let t=this.o,e=this.t;if(D&&t===void 0){let s=e!==void 0&&e.length===1;s&&(t=at.get(e)),t===void 0&&((this.o=t=new CSSStyleSheet).replaceSync(this.cssText),s&&at.set(e,t))}return t}toString(){return this.cssText}},ct=i=>new k(typeof i=="string"?i:i+"",void 0,q),M=(i,...t)=>{let e=i.length===1?i[0]:t.reduce((s,n,o)=>s+(r=>{if(r._$cssResult$===!0)return r.cssText;if(typeof r=="number")return r;throw Error("Value passed to 'css' function must be a 'css' function result: "+r+". Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.")})(n)+i[o+1],i[0]);return new k(e,i,q)},lt=(i,t)=>{if(D)i.adoptedStyleSheets=t.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let e of t){let s=document.createElement("style"),n=B.litNonce;n!==void 0&&s.setAttribute("nonce",n),s.textContent=e.cssText,i.appendChild(s)}},X=D?i=>i:i=>i instanceof CSSStyleSheet?(t=>{let e="";for(let s of t.cssRules)e+=s.cssText;return ct(e)})(i):i;var{is:kt,defineProperty:Mt,getOwnPropertyDescriptor:Ht,getOwnPropertyNames:Ut,getOwnPropertySymbols:Ot,getPrototypeOf:Rt}=Object,V=globalThis,ht=V.trustedTypes,Nt=ht?ht.emptyScript:"",Tt=V.reactiveElementPolyfillSupport,H=(i,t)=>i,G={toAttribute(i,t){switch(t){case Boolean:i=i?Nt:null;break;case Object:case Array:i=i==null?i:JSON.stringify(i)}return i},fromAttribute(i,t){let e=i;switch(t){case Boolean:e=i!==null;break;case Number:e=i===null?null:Number(i);break;case Object:case Array:try{e=JSON.parse(i)}catch{e=null}}return e}},dt=(i,t)=>!kt(i,t),pt={attribute:!0,type:String,converter:G,reflect:!1,useDefault:!1,hasChanged:dt};Symbol.metadata??=Symbol("metadata"),V.litPropertyMetadata??=new WeakMap;var v=class extends HTMLElement{static addInitializer(t){this._$Ei(),(this.l??=[]).push(t)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(t,e=pt){if(e.state&&(e.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(t)&&((e=Object.create(e)).wrapped=!0),this.elementProperties.set(t,e),!e.noAccessor){let s=Symbol(),n=this.getPropertyDescriptor(t,s,e);n!==void 0&&Mt(this.prototype,t,n)}}static getPropertyDescriptor(t,e,s){let{get:n,set:o}=Ht(this.prototype,t)??{get(){return this[e]},set(r){this[e]=r}};return{get:n,set(r){let c=n?.call(this);o?.call(this,r),this.requestUpdate(t,c,s)},configurable:!0,enumerable:!0}}static getPropertyOptions(t){return this.elementProperties.get(t)??pt}static _$Ei(){if(this.hasOwnProperty(H("elementProperties")))return;let t=Rt(this);t.finalize(),t.l!==void 0&&(this.l=[...t.l]),this.elementProperties=new Map(t.elementProperties)}static finalize(){if(this.hasOwnProperty(H("finalized")))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(H("properties"))){let e=this.properties,s=[...Ut(e),...Ot(e)];for(let n of s)this.createProperty(n,e[n])}let t=this[Symbol.metadata];if(t!==null){let e=litPropertyMetadata.get(t);if(e!==void 0)for(let[s,n]of e)this.elementProperties.set(s,n)}this._$Eh=new Map;for(let[e,s]of this.elementProperties){let n=this._$Eu(e,s);n!==void 0&&this._$Eh.set(n,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(t){let e=[];if(Array.isArray(t)){let s=new Set(t.flat(1/0).reverse());for(let n of s)e.unshift(X(n))}else t!==void 0&&e.push(X(t));return e}static _$Eu(t,e){let s=e.attribute;return s===!1?void 0:typeof s=="string"?s:typeof t=="string"?t.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(t=>this.enableUpdating=t),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(t=>t(this))}addController(t){(this._$EO??=new Set).add(t),this.renderRoot!==void 0&&this.isConnected&&t.hostConnected?.()}removeController(t){this._$EO?.delete(t)}_$E_(){let t=new Map,e=this.constructor.elementProperties;for(let s of e.keys())this.hasOwnProperty(s)&&(t.set(s,this[s]),delete this[s]);t.size>0&&(this._$Ep=t)}createRenderRoot(){let t=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return lt(t,this.constructor.elementStyles),t}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(t=>t.hostConnected?.())}enableUpdating(t){}disconnectedCallback(){this._$EO?.forEach(t=>t.hostDisconnected?.())}attributeChangedCallback(t,e,s){this._$AK(t,s)}_$ET(t,e){let s=this.constructor.elementProperties.get(t),n=this.constructor._$Eu(t,s);if(n!==void 0&&s.reflect===!0){let o=(s.converter?.toAttribute!==void 0?s.converter:G).toAttribute(e,s.type);this._$Em=t,o==null?this.removeAttribute(n):this.setAttribute(n,o),this._$Em=null}}_$AK(t,e){let s=this.constructor,n=s._$Eh.get(t);if(n!==void 0&&this._$Em!==n){let o=s.getPropertyOptions(n),r=typeof o.converter=="function"?{fromAttribute:o.converter}:o.converter?.fromAttribute!==void 0?o.converter:G;this._$Em=n;let c=r.fromAttribute(e,o.type);this[n]=c??this._$Ej?.get(n)??c,this._$Em=null}}requestUpdate(t,e,s,n=!1,o){if(t!==void 0){let r=this.constructor;if(n===!1&&(o=this[t]),s??=r.getPropertyOptions(t),!((s.hasChanged??dt)(o,e)||s.useDefault&&s.reflect&&o===this._$Ej?.get(t)&&!this.hasAttribute(r._$Eu(t,s))))return;this.C(t,e,s)}this.isUpdatePending===!1&&(this._$ES=this._$EP())}C(t,e,{useDefault:s,reflect:n,wrapped:o},r){s&&!(this._$Ej??=new Map).has(t)&&(this._$Ej.set(t,r??e??this[t]),o!==!0||r!==void 0)||(this._$AL.has(t)||(this.hasUpdated||s||(e=void 0),this._$AL.set(t,e)),n===!0&&this._$Em!==t&&(this._$Eq??=new Set).add(t))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let t=this.scheduleUpdate();return t!=null&&await t,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[n,o]of this._$Ep)this[n]=o;this._$Ep=void 0}let s=this.constructor.elementProperties;if(s.size>0)for(let[n,o]of s){let{wrapped:r}=o,c=this[n];r!==!0||this._$AL.has(n)||c===void 0||this.C(n,void 0,o,c)}}let t=!1,e=this._$AL;try{t=this.shouldUpdate(e),t?(this.willUpdate(e),this._$EO?.forEach(s=>s.hostUpdate?.()),this.update(e)):this._$EM()}catch(s){throw t=!1,this._$EM(),s}t&&this._$AE(e)}willUpdate(t){}_$AE(t){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(t)),this.updated(t)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(t){return!0}update(t){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(t){}firstUpdated(t){}};v.elementStyles=[],v.shadowRootOptions={mode:"open"},v[H("elementProperties")]=new Map,v[H("finalized")]=new Map,Tt?.({ReactiveElement:v}),(V.reactiveElementVersions??=[]).push("2.1.2");var st=globalThis,ut=i=>i,j=st.trustedTypes,mt=j?j.createPolicy("lit-html",{createHTML:i=>i}):void 0,vt="$lit$",w=`lit$${Math.random().toFixed(9).slice(2)}$`,bt="?"+w,zt=`<${bt}>`,S=document,O=()=>S.createComment(""),R=i=>i===null||typeof i!="object"&&typeof i!="function",nt=Array.isArray,Ft=i=>nt(i)||typeof i?.[Symbol.iterator]=="function",J=`[ 	
\f\r]`,U=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,ft=/-->/g,gt=/>/g,x=RegExp(`>|${J}(?:([^\\s"'>=/]+)(${J}*=${J}*(?:[^ 	
\f\r"'\`<>=]|("|')|))|$)`,"g"),_t=/'/g,$t=/"/g,wt=/^(?:script|style|textarea|title)$/i,it=i=>(t,...e)=>({_$litType$:i,strings:t,values:e}),p=it(1),Zt=it(2),Qt=it(3),C=Symbol.for("lit-noChange"),l=Symbol.for("lit-nothing"),yt=new WeakMap,A=S.createTreeWalker(S,129);function xt(i,t){if(!nt(i)||!i.hasOwnProperty("raw"))throw Error("invalid template strings array");return mt!==void 0?mt.createHTML(t):t}var Lt=(i,t)=>{let e=i.length-1,s=[],n,o=t===2?"<svg>":t===3?"<math>":"",r=U;for(let c=0;c<e;c++){let a=i[c],h,u,d=-1,$=0;for(;$<a.length&&(r.lastIndex=$,u=r.exec(a),u!==null);)$=r.lastIndex,r===U?u[1]==="!--"?r=ft:u[1]!==void 0?r=gt:u[2]!==void 0?(wt.test(u[2])&&(n=RegExp("</"+u[2],"g")),r=x):u[3]!==void 0&&(r=x):r===x?u[0]===">"?(r=n??U,d=-1):u[1]===void 0?d=-2:(d=r.lastIndex-u[2].length,h=u[1],r=u[3]===void 0?x:u[3]==='"'?$t:_t):r===$t||r===_t?r=x:r===ft||r===gt?r=U:(r=x,n=void 0);let y=r===x&&i[c+1].startsWith("/>")?" ":"";o+=r===U?a+zt:d>=0?(s.push(h),a.slice(0,d)+vt+a.slice(d)+w+y):a+w+(d===-2?c:y)}return[xt(i,o+(i[e]||"<?>")+(t===2?"</svg>":t===3?"</math>":"")),s]},N=class i{constructor({strings:t,_$litType$:e},s){let n;this.parts=[];let o=0,r=0,c=t.length-1,a=this.parts,[h,u]=Lt(t,e);if(this.el=i.createElement(h,s),A.currentNode=this.el.content,e===2||e===3){let d=this.el.content.firstChild;d.replaceWith(...d.childNodes)}for(;(n=A.nextNode())!==null&&a.length<c;){if(n.nodeType===1){if(n.hasAttributes())for(let d of n.getAttributeNames())if(d.endsWith(vt)){let $=u[r++],y=n.getAttribute(d).split(w),b=/([.?@])?(.*)/.exec($);a.push({type:1,index:o,name:b[2],strings:y,ctor:b[1]==="."?Q:b[1]==="?"?Y:b[1]==="@"?tt:P}),n.removeAttribute(d)}else d.startsWith(w)&&(a.push({type:6,index:o}),n.removeAttribute(d));if(wt.test(n.tagName)){let d=n.textContent.split(w),$=d.length-1;if($>0){n.textContent=j?j.emptyScript:"";for(let y=0;y<$;y++)n.append(d[y],O()),A.nextNode(),a.push({type:2,index:++o});n.append(d[$],O())}}}else if(n.nodeType===8)if(n.data===bt)a.push({type:2,index:o});else{let d=-1;for(;(d=n.data.indexOf(w,d+1))!==-1;)a.push({type:7,index:o}),d+=w.length-1}o++}}static createElement(t,e){let s=S.createElement("template");return s.innerHTML=t,s}};function E(i,t,e=i,s){if(t===C)return t;let n=s!==void 0?e._$Co?.[s]:e._$Cl,o=R(t)?void 0:t._$litDirective$;return n?.constructor!==o&&(n?._$AO?.(!1),o===void 0?n=void 0:(n=new o(i),n._$AT(i,e,s)),s!==void 0?(e._$Co??=[])[s]=n:e._$Cl=n),n!==void 0&&(t=E(i,n._$AS(i,t.values),n,s)),t}var Z=class{constructor(t,e){this._$AV=[],this._$AN=void 0,this._$AD=t,this._$AM=e}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(t){let{el:{content:e},parts:s}=this._$AD,n=(t?.creationScope??S).importNode(e,!0);A.currentNode=n;let o=A.nextNode(),r=0,c=0,a=s[0];for(;a!==void 0;){if(r===a.index){let h;a.type===2?h=new T(o,o.nextSibling,this,t):a.type===1?h=new a.ctor(o,a.name,a.strings,this,t):a.type===6&&(h=new et(o,this,t)),this._$AV.push(h),a=s[++c]}r!==a?.index&&(o=A.nextNode(),r++)}return A.currentNode=S,n}p(t){let e=0;for(let s of this._$AV)s!==void 0&&(s.strings!==void 0?(s._$AI(t,s,e),e+=s.strings.length-2):s._$AI(t[e])),e++}},T=class i{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(t,e,s,n){this.type=2,this._$AH=l,this._$AN=void 0,this._$AA=t,this._$AB=e,this._$AM=s,this.options=n,this._$Cv=n?.isConnected??!0}get parentNode(){let t=this._$AA.parentNode,e=this._$AM;return e!==void 0&&t?.nodeType===11&&(t=e.parentNode),t}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(t,e=this){t=E(this,t,e),R(t)?t===l||t==null||t===""?(this._$AH!==l&&this._$AR(),this._$AH=l):t!==this._$AH&&t!==C&&this._(t):t._$litType$!==void 0?this.$(t):t.nodeType!==void 0?this.T(t):Ft(t)?this.k(t):this._(t)}O(t){return this._$AA.parentNode.insertBefore(t,this._$AB)}T(t){this._$AH!==t&&(this._$AR(),this._$AH=this.O(t))}_(t){this._$AH!==l&&R(this._$AH)?this._$AA.nextSibling.data=t:this.T(S.createTextNode(t)),this._$AH=t}$(t){let{values:e,_$litType$:s}=t,n=typeof s=="number"?this._$AC(t):(s.el===void 0&&(s.el=N.createElement(xt(s.h,s.h[0]),this.options)),s);if(this._$AH?._$AD===n)this._$AH.p(e);else{let o=new Z(n,this),r=o.u(this.options);o.p(e),this.T(r),this._$AH=o}}_$AC(t){let e=yt.get(t.strings);return e===void 0&&yt.set(t.strings,e=new N(t)),e}k(t){nt(this._$AH)||(this._$AH=[],this._$AR());let e=this._$AH,s,n=0;for(let o of t)n===e.length?e.push(s=new i(this.O(O()),this.O(O()),this,this.options)):s=e[n],s._$AI(o),n++;n<e.length&&(this._$AR(s&&s._$AB.nextSibling,n),e.length=n)}_$AR(t=this._$AA.nextSibling,e){for(this._$AP?.(!1,!0,e);t!==this._$AB;){let s=ut(t).nextSibling;ut(t).remove(),t=s}}setConnected(t){this._$AM===void 0&&(this._$Cv=t,this._$AP?.(t))}},P=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(t,e,s,n,o){this.type=1,this._$AH=l,this._$AN=void 0,this.element=t,this.name=e,this._$AM=n,this.options=o,s.length>2||s[0]!==""||s[1]!==""?(this._$AH=Array(s.length-1).fill(new String),this.strings=s):this._$AH=l}_$AI(t,e=this,s,n){let o=this.strings,r=!1;if(o===void 0)t=E(this,t,e,0),r=!R(t)||t!==this._$AH&&t!==C,r&&(this._$AH=t);else{let c=t,a,h;for(t=o[0],a=0;a<o.length-1;a++)h=E(this,c[s+a],e,a),h===C&&(h=this._$AH[a]),r||=!R(h)||h!==this._$AH[a],h===l?t=l:t!==l&&(t+=(h??"")+o[a+1]),this._$AH[a]=h}r&&!n&&this.j(t)}j(t){t===l?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,t??"")}},Q=class extends P{constructor(){super(...arguments),this.type=3}j(t){this.element[this.name]=t===l?void 0:t}},Y=class extends P{constructor(){super(...arguments),this.type=4}j(t){this.element.toggleAttribute(this.name,!!t&&t!==l)}},tt=class extends P{constructor(t,e,s,n,o){super(t,e,s,n,o),this.type=5}_$AI(t,e=this){if((t=E(this,t,e,0)??l)===C)return;let s=this._$AH,n=t===l&&s!==l||t.capture!==s.capture||t.once!==s.once||t.passive!==s.passive,o=t!==l&&(s===l||n);n&&this.element.removeEventListener(this.name,this,s),o&&this.element.addEventListener(this.name,this,t),this._$AH=t}handleEvent(t){typeof this._$AH=="function"?this._$AH.call(this.options?.host??this.element,t):this._$AH.handleEvent(t)}},et=class{constructor(t,e,s){this.element=t,this.type=6,this._$AN=void 0,this._$AM=e,this.options=s}get _$AU(){return this._$AM._$AU}_$AI(t){E(this,t)}};var It=st.litHtmlPolyfillSupport;It?.(N,T),(st.litHtmlVersions??=[]).push("3.3.3");var At=(i,t,e)=>{let s=e?.renderBefore??t,n=s._$litPart$;if(n===void 0){let o=e?.renderBefore??null;s._$litPart$=n=new T(t.insertBefore(O(),o),o,void 0,e??{})}return n._$AI(i),n};var ot=globalThis,_=class extends v{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let t=super.createRenderRoot();return this.renderOptions.renderBefore??=t.firstChild,t}update(t){let e=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(t),this._$Do=At(e,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return C}};_._$litElement$=!0,_.finalized=!0,ot.litElementHydrateSupport?.({LitElement:_});var Bt=ot.litElementPolyfillSupport;Bt?.({LitElement:_});(ot.litElementVersions??=[]).push("4.2.2");function Dt(i,t,e){return Math.min(Math.max(i,t),e)}function K(i,t,e){return e<=t?.5:Dt((i-t)/(e-t),0,1)}function Vt(i,t,e){if(i==null)return"unknown";if(i<t)return"below";if(i>e)return"above";let s=e-t;if(s<=0)return"in_band";let n=(i-t)/s;return n<.25?"cool_edge":n>.75?"warm_edge":"in_band"}function St(i){let{operative:t,setpoint:e,low:s,high:n}=i;if(s==null||n==null||n<=s)return null;let o=s-1.5,r=n+1.5;return{low:s,high:n,span:n-s,operative:t,setpoint:e,category:i.category??"",verdict:Vt(t,s,n),axisLow:o,axisHigh:r,lowFrac:K(s,o,r),highFrac:K(n,o,r),operativeFrac:t==null?null:K(t,o,r),setpointFrac:e==null?null:K(e,o,r)}}var Ct={in_band:"In comfort band",cool_edge:"Cool edge of band",warm_edge:"Warm edge of band",below:"Below comfort band",above:"Above comfort band",unknown:"No reading",preheating:"Pre-heating",coasting:"Coasting",window:"Window open",failure:"Heating failure",learning:"Learning",shadow:"Shadow active",setpoint:"Setpoint",no_entity:"Select a Poise thermostat entity.",min_left:"min",no_system:"Select the Poise System sensor.",sys_title:"Poise System",demand_on:"Boiler demand",demand_off:"No demand",frost:"Frost override",zones:"zones",heating_n:"heating",flow:"Flow",shed:"shed",shadow_would:"would"},jt={in_band:"Im Komfortband",cool_edge:"Untere Bandkante",warm_edge:"Obere Bandkante",below:"Unter dem Komfortband",above:"\xDCber dem Komfortband",unknown:"Kein Messwert",preheating:"Vorheizen",coasting:"Auslaufen",window:"Fenster offen",failure:"Heizausfall",learning:"Lernt",shadow:"Shadow aktiv",setpoint:"Sollwert",no_entity:"Bitte eine Poise-Thermostat-Entit\xE4t w\xE4hlen.",min_left:"Min",no_system:"Bitte den Poise-System-Sensor w\xE4hlen.",sys_title:"Poise System",demand_on:"Kesselbedarf",demand_off:"Kein Bedarf",frost:"Frost-Override",zones:"Zonen",heating_n:"heizen",flow:"Vorlauf",shed:"abgeworfen",shadow_would:"w\xFCrde"};function m(i,t){return((i??"en").toLowerCase().startsWith("de")?jt:Ct)[t]??Ct[t]??t}var Kt=[{name:"entity",required:!0,selector:{entity:{domain:"climate"}}},{name:"show_shadow",selector:{boolean:{}}}],W=class extends _{setConfig(t){this._config=t}shouldUpdate(t){return t.has("hass")||t.has("_config")}_changed(t){this.dispatchEvent(new CustomEvent("config-changed",{detail:{config:t.detail.value}}))}render(){return!this.hass||!this._config?p``:p`<ha-form
      .hass=${this.hass}
      .data=${this._config}
      .schema=${Kt}
      .computeLabel=${t=>t.name}
      @value-changed=${this._changed}
    ></ha-form>`}};W.properties={hass:{},_config:{state:!0}};customElements.get("poise-card-editor")||customElements.define("poise-card-editor",W);function z(i){let t=typeof i=="string"?parseFloat(i):i;return typeof t=="number"&&!Number.isNaN(t)?t:null}var F=class extends _{static getStubConfig(t){return{type:"custom:poise-system-card",entity:Object.keys(t.states).find(s=>s.startsWith("binary_sensor.")&&t.states[s].attributes.zone_count!==void 0)??""}}setConfig(t){if(!t)throw new Error("Invalid configuration");this._config=t}getCardSize(){return 2}shouldUpdate(t){if(t.has("_config"))return!0;let e=t.get("hass");return!e||!this._config?.entity?!0:e.states[this._config.entity]!==this.hass.states[this._config.entity]}_moreInfo(){this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}render(){let t=this.hass?.locale?.language,e=this._config?.entity,s=e?this.hass.states[e]:void 0;if(!s)return p`<ha-card
        ><div class="empty">${m(t,"no_system")}</div></ha-card
      >`;let n=s.attributes,o=s.state==="on",r=z(n.flow_target),c=z(n.shed_count)??0,a=n.source_grants??{},h=Object.keys(a);return p`<ha-card .header=${m(t,"sys_title")}>
      <div class="wrap" @click=${this._moreInfo}>
        <div class="state ${o?"on":""}">
          <ha-icon icon=${o?"mdi:fire":"mdi:fire-off"}></ha-icon>
          <span>${o?m(t,"demand_on"):m(t,"demand_off")}</span>
          ${n.frost_override?p`<em class="frost">${m(t,"frost")}</em>`:l}
        </div>
        <div class="stats">
          <div>
            <strong>${z(n.active_zones)??0}</strong
            ><span>${m(t,"heating_n")}</span>
          </div>
          <div>
            <strong
              >${z(n.controlling_zones)??0}/${z(n.zone_count)??0}</strong
            ><span>${m(t,"zones")}</span>
          </div>
          ${r!=null?p`<div>
                <strong>${r.toFixed(0)}°</strong><span>${m(t,"flow")}</span>
              </div>`:l}
          ${c>0?p`<div>
                <strong>${c}</strong><span>${m(t,"shed")}</span>
              </div>`:l}
        </div>
        ${h.length?p`<div class="grants">
              ${h.map(u=>p`<span class="chip">${u}: ${a[u]}</span>`)}
            </div>`:l}
      </div>
    </ha-card>`}};F.properties={hass:{},_config:{state:!0}},F.styles=M`
    .wrap { padding: 8px 16px 16px; cursor: pointer; }
    .state { display: flex; align-items: center; gap: 8px; font-size: 18px; }
    .state ha-icon { --mdc-icon-size: 22px; color: var(--secondary-text-color); }
    .state.on ha-icon { color: var(--error-color, #d33); }
    .frost { font-style: normal; margin-left: auto; padding: 2px 8px; border-radius: 10px;
      font-size: 11px; background: var(--info-color, #2196f3); color: var(--text-primary-color, #fff); }
    .stats { display: flex; gap: 18px; margin-top: 10px; flex-wrap: wrap; }
    .stats strong { font-size: 20px; }
    .stats span { display: block; font-size: 11px; color: var(--secondary-text-color); }
    .grants { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
    .chip { padding: 3px 8px; border-radius: 12px; font-size: 12px;
      background: var(--secondary-background-color); }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;customElements.get("poise-system-card")||customElements.define("poise-system-card",F);window.customCards=window.customCards||[];window.customCards.push({type:"poise-system-card",name:"Poise System",preview:!0,description:"Multi-zone boiler demand, flow & load shedding for the Poise hub."});function Et(i,t,e){return Math.min(Math.max(i,t),e)}function Pt(i,t,e,s=300,n=90,o=1){let r=[];for(let g of i)g.op!=null&&r.push(g.op),g.sp!=null&&r.push(g.sp);if(t!=null&&r.push(t),e!=null&&r.push(e),r.length===0||i.length===0)return null;let c=Math.min(...r)-o,a=Math.max(...r)+o,h=i[0].t,d=i[i.length-1].t-h||1,$=a-c||1,y=g=>(g-h)/d*s,b=g=>n-(g-c)/$*n,rt=g=>i.filter(I=>g(I)!=null).map(I=>`${y(I.t).toFixed(1)},${b(g(I)).toFixed(1)}`).join(" ");return{width:s,height:n,opPath:rt(g=>g.op),spPath:rt(g=>g.sp),bandTop:e==null?0:Et(b(e),0,n),bandBottom:t==null?n:Et(b(t),0,n),vMin:c,vMax:a}}var Wt="0.51.0";function f(i){let t=typeof i=="string"?parseFloat(i):i;return typeof t=="number"&&!Number.isNaN(t)?t:null}var L=class extends _{constructor(){super(...arguments);this._history=[];this._histFor=null}static getConfigElement(){return document.createElement("poise-card-editor")}static getStubConfig(e){return{type:"custom:poise-card",entity:Object.keys(e.states).find(n=>n.startsWith("climate.")&&e.states[n].attributes.comfort_low!==void 0)??"",show_shadow:!0}}setConfig(e){if(!e)throw new Error("Invalid configuration");if(e.entity&&!e.entity.startsWith("climate."))throw new Error("Poise card: entity must be a climate entity");this._config={show_shadow:!0,...e}}getCardSize(){return 4}shouldUpdate(e){if(e.has("_config"))return!0;let s=e.get("hass");return!s||!this._config?.entity?!0:s.states[this._config.entity]!==this.hass.states[this._config.entity]}_setpoint(e){let s=this._config.entity;if(!s)return;let n=this.hass.states[s],o=f(n.attributes.target_temperature_step)??.5,r=f(n.attributes.heat_sp)??f(n.attributes.temperature)??21;this.hass.callService("climate","set_temperature",{entity_id:s,temperature:Math.round((r+e*o)*10)/10})}updated(){let e=this._config?.entity;e&&this.hass&&this._histFor!==e&&(this._histFor=e,this._loadHistory(e))}async _loadHistory(e){if(!this.hass.connection)return;let s=new Date,n=new Date(s.getTime()-24*3600*1e3);try{let r=(await this.hass.connection.sendMessagePromise({type:"history/history_during_period",start_time:n.toISOString(),end_time:s.toISOString(),entity_ids:[e],minimal_response:!1,no_attributes:!1}))?.[e]??[],c={},a=[];for(let h of r){h.a&&(c={...c,...h.a});let u=(f(h.lu)??f(h.lc)??0)*1e3;a.push({t:u,op:f(c.operative_temperature)??f(c.current_temperature),sp:f(c.heat_sp)??f(c.temperature)})}this._history=a,this.requestUpdate()}catch{}}_moreInfo(){this._config.entity&&this.dispatchEvent(new CustomEvent("hass-more-info",{detail:{entityId:this._config.entity},bubbles:!0,composed:!0}))}_chart(e,s){let n=Pt(this._history,e,s,300,80);return n?p`<svg
      class="chart"
      viewBox="0 0 ${n.width} ${n.height}"
      preserveAspectRatio="none"
    >
      <rect
        x="0"
        y=${n.bandTop}
        width=${n.width}
        height=${Math.max(0,n.bandBottom-n.bandTop)}
        class="cband"
      ></rect>
      <polyline points=${n.spPath} class="csp"></polyline>
      <polyline points=${n.opPath} class="cop"></polyline>
    </svg>`:l}render(){let e=this.hass?.locale?.language,s=this._config?.entity,n=s?this.hass.states[s]:void 0;if(!n)return p`<ha-card
        ><div class="empty">${m(e,"no_entity")}</div></ha-card
      >`;let o=n.attributes,r=f(o.operative_temperature)??f(o.current_temperature),c=f(o.heat_sp)??f(o.temperature),a=St({operative:r,setpoint:c,low:f(o.comfort_low),high:f(o.comfort_high),category:o.category??null});return p`<ha-card .header=${o.friendly_name??"Poise"}>
      <div class="wrap">
        ${this._hero(a,e)}
        <div class="big">
          ${r!=null?r.toFixed(1):"\u2014"}<span>°C</span>
        </div>
        <div class="verdict">
          ${a?m(e,a.verdict):m(e,"unknown")}
          ${a?.category?p`<span class="cat">Kat. ${a.category}</span>`:l}
        </div>
        ${this._control(c,e)}
        ${this._chart(f(o.comfort_low),f(o.comfort_high))}
        ${this._chips(o,e)}
        ${this._learn(o,e)}
      </div>
    </ha-card>`}_hero(e,s){if(!e)return l;let n=o=>`${(o*100).toFixed(1)}%`;return p`<div class="band">
      <div
        class="fill"
        style="left:${n(e.lowFrac)};right:${n(1-e.highFrac)}"
      ></div>
      ${e.setpointFrac!=null?p`<div class="mark sp" style="left:${n(e.setpointFrac)}"></div>`:l}
      ${e.operativeFrac!=null?p`<div class="mark op" style="left:${n(e.operativeFrac)}"></div>`:l}
      <div class="tick" style="left:${n(e.lowFrac)}">${e.low.toFixed(0)}</div>
      <div class="tick" style="left:${n(e.highFrac)}">${e.high.toFixed(0)}</div>
    </div>`}_control(e,s){return p`<div class="ctl">
      <ha-icon-button @click=${()=>this._setpoint(-1)} label="-">
        <ha-icon icon="mdi:minus"></ha-icon>
      </ha-icon-button>
      <div class="sp">
        <span>${m(s,"setpoint")}</span
        ><strong>${e!=null?e.toFixed(1):"\u2014"}°C</strong>
      </div>
      <ha-icon-button @click=${()=>this._setpoint(1)} label="+">
        <ha-icon icon="mdi:plus"></ha-icon>
      </ha-icon-button>
    </div>`}_chips(e,s){let n=[];e.preheating&&n.push(this._chip("mdi:fire-circle",m(s,"preheating"),e.minutes_to_comfort,s)),e.coasting&&n.push(this._chip("mdi:coffee",m(s,"coasting"),e.minutes_to_setback,s)),e.window_open&&n.push(this._chip("mdi:window-open",m(s,"window"))),e.heating_failure&&n.push(this._chip("mdi:alert",m(s,"failure")));let o=e.binding_lower_cause;return o&&o!=="en16798"&&n.push(this._chip("mdi:shield-alert",String(o))),n.length?p`<div class="chips" @click=${this._moreInfo}>${n}</div>`:l}_chip(e,s,n,o){let r=f(n);return p`<div class="chip">
      <ha-icon icon=${e}></ha-icon><span>${s}</span>
      ${r!=null?p`<em>${Math.round(r)} ${m(o,"min_left")}</em>`:l}
    </div>`}_learn(e,s){let n=f(e.confidence),o=this._config.show_shadow&&(e.mpc_active||e.tpi_active||e.pi_active),r=f(e.pi_setpoint),c=f(e.mpc_setpoint),a=e.tpi_active?`TPI ${Math.round(f(e.tpi_valve_percent)??0)}%`:e.pi_active&&r!=null?`PI ${r.toFixed(1)}\xB0`:e.mpc_active&&c!=null?`MPC ${c.toFixed(1)}\xB0`:"";return p`<div class="learn">
      ${n!=null?p`<div class="bar">
            <i style="width:${(n*100).toFixed(0)}%"></i>
          </div>
          <span>${m(s,"learning")} ${(n*100).toFixed(0)}%</span>`:l}
      ${o?p`<div class="pill">
            ${m(s,"shadow")}${a?p` · ${a}`:l}
          </div>`:l}
    </div>`}};L.properties={hass:{},_config:{state:!0}},L.styles=M`
    .wrap { padding: 8px 16px 16px; }
    .band {
      position: relative; height: 26px; margin: 8px 0 22px;
      border-radius: 13px; background: var(--divider-color, #e0e0e0);
    }
    .fill {
      position: absolute; top: 0; bottom: 0; border-radius: 13px;
      background: color-mix(in srgb, var(--success-color, #4caf50) 35%, transparent);
    }
    .mark { position: absolute; top: -3px; width: 4px; height: 32px; border-radius: 2px; transform: translateX(-2px); }
    .mark.op { background: var(--primary-color, #2196f3); }
    .mark.sp { background: var(--secondary-text-color, #888); }
    .tick { position: absolute; top: 28px; font-size: 11px; color: var(--secondary-text-color); transform: translateX(-50%); }
    .big { font-size: 40px; font-weight: 600; line-height: 1; }
    .big span { font-size: 18px; color: var(--secondary-text-color); }
    .verdict { color: var(--secondary-text-color); margin-bottom: 8px; }
    .cat { margin-left: 8px; opacity: 0.8; }
    .ctl { display: flex; align-items: center; justify-content: center; gap: 18px; margin: 10px 0 4px; }
    .sp { text-align: center; }
    .sp span { display: block; font-size: 12px; color: var(--secondary-text-color); }
    .sp strong { font-size: 20px; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
    .chip { display: inline-flex; align-items: center; gap: 4px; padding: 3px 8px;
      border-radius: 14px; background: var(--secondary-background-color); font-size: 13px; }
    .chip ha-icon { --mdc-icon-size: 16px; }
    .chip em { font-style: normal; color: var(--secondary-text-color); }
    .learn { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
    .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--divider-color); overflow: hidden; }
    .bar i { display: block; height: 100%; background: var(--primary-color); }
    .learn span { font-size: 12px; color: var(--secondary-text-color); }
    .pill { padding: 2px 8px; border-radius: 10px; font-size: 11px;
      background: var(--primary-color); color: var(--text-primary-color, #fff); }
    .chart { width: 100%; height: 80px; margin: 10px 0 2px; display: block; }
    .cband { fill: color-mix(in srgb, var(--success-color, #4caf50) 16%, transparent); }
    .cop { fill: none; stroke: var(--primary-color, #2196f3); stroke-width: 2; vector-effect: non-scaling-stroke; }
    .csp { fill: none; stroke: var(--secondary-text-color, #888); stroke-width: 1.5; stroke-dasharray: 3 3; vector-effect: non-scaling-stroke; }
    .chips { cursor: pointer; }
    .empty { padding: 24px 16px; color: var(--secondary-text-color); }
  `;window.customCards=window.customCards||[];window.customCards.push({type:"poise-card",name:"Poise Thermostat",preview:!0,description:"EN-16798 comfort band, operative temperature & shadow state for Poise."});customElements.get("poise-card")||customElements.define("poise-card",L);console.info(`%c POISE-CARD ${Wt} `,"background:#2196f3;color:#fff");export{L as PoiseCard};
